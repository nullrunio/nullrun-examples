"""ToolBlock demo: block/allow decisions + executions/traces/audit records.

Like ``gate_check_demo.py`` this script probes ``/api/v1/gate`` once per
tool name and prints block/allow on stdout. Unlike that script each tool
is wrapped in ``@nullrun.protect`` so the SDK records the event on the
wire:

ALLOW path
==========
  * ``check_workflow_budget`` runs ``/gate`` with ``tools=[<name>]``
    and gets ``decision=allow``.
  * ``span_start`` is emitted (best-effort, never blocks).
  * The stub body runs.
  * ``runtime.track_tool(name, ...)`` posts a ``tool_call`` event to
    ``/track/batch`` → outbox drain → ``cost_events`` row.
  * ``span_end`` is emitted.
  * Net result: ``cost_events`` row + ``span_start`` / ``span_end``
    pair + optional audit event (depending on the
    ``NULLRUN_AUDIT_ALLOW_DECISIONS_ENABLED`` flag — see
    ``CLAUDE.md`` §24).

BLOCK path (TOOL_BLOCKED via the workflow's ``tool_patterns``)
==============================================================
  * ``check_workflow_budget`` runs ``/gate`` and gets
    ``403 TOOL_BLOCKED``. The server returns the killing rule's
    identifier (e.g. ``rule_kind="pattern_match"`` or
    ``"policy_cache_miss"``).
  * ``WorkflowKilledInterrupt`` (BaseException) propagates out of
    ``check_workflow_budget``. ``@protect``'s sync wrapper re-wraps
    it as ``NullRunBlockedException`` so generic
    ``except Exception:`` clauses catch it.
  * ``runtime._emit_sdk_error`` fires the Layer-2 audit hook →
    ``audit_events`` row (Refusal = EnforcementEvidence, mandatory
    per ADR-009 §6 + INV-3 — the allow-skim flag does NOT skip
    refusals).
  * The ``finally`` clause emits ``span_end`` with the kill reason.
  * ``track_tool`` is NOT called (body never ran).
  * Net result: NO ``cost_events`` row. You DO get ``audit_events``
    and a partial ``span_end`` on the trace timeline.

What to look at in the dashboard
================================
After the script finishes, the workflow id is the same one the API key
is bound to (in the previous run it was ``e4ada1c0-…9010``). Open three
views:

  /control-center/executions?workflow=<workflow_id>&since=<now>
    → one ``cost_events`` row per ALLOWED call. Blocked tools are
      absent (no body, no track).

  /control-center/traces?workflow=<workflow_id>&since=<now>
    → spans for BOTH paths. Allowed tools show the full
      ``span_start``+``span_end`` pair; blocked tools show only
      ``span_end`` with the kill reason in ``error``.

  /control-center/audit?workflow=<workflow_id>&since=<now>
    → audit events for BOTH paths (mandatory per INV-3).

Prerequisites
=============
  * ``NULLRUN_API_KEY`` exported (a key bound to a workflow that has
    a ``tool_block`` policy with a pattern matching ``"bash"`` /
    ``"bash*"`` — same shape as ``gate_check_demo.py`` expects).
  * No LLM keys needed: the stub returns immediately.

Run:
    pip install nullrun
    export NULLRUN_API_KEY=nr_live_...
    python examples/tool_block_records_demo.py [tool_name_1 tool_name_2 ...]

Defaults probe the same set ``gate_check_demo.py`` uses:
``bash, bash.foo, sh, shell, shell.foo, read_file,
filesystem.delete_user``. Override on the CLI to probe any other name.
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import sys

from nullrun import (
    protect,
    set_call_context,
    shutdown,
)
from nullrun.breaker.exceptions import (
    NullRunBlockedException,
    NullRunError,
)


DEFAULT_TOOLS = [
    "bash",
    "bash.foo",
    "sh",
    "shell",
    "shell.foo",
    "read_file",
    "filesystem.delete_user",
]


def _make_protected_tool(name: str):
    """Wrap a stub for ``name`` in ``@nullrun.protect``.

    Note: ``@protect`` auto-populates the ``tools`` contextvar from
    ``fn.__name__`` when the caller has not set it explicitly — see
    decorators.py F03 fix (~line 484). The explicit
    ``set_call_context(tools=[name])`` in ``probe()`` is harmless
    and matches the shape ``gate_check_demo.py`` uses.
    """
    def stub(*args, **kwargs):
        return f"simulated-{name}"
    stub.__name__ = name
    return protect(stub)


def probe(name: str) -> None:
    fn = _make_protected_tool(name)
    set_call_context(tools=[name])
    try:
        result = fn()
        # ALLOW path — @protect already posted /track (cost_events)
        # and the span_start/span_end pair on the wire.
        print(f"[nullrun] tool={name} decision=allow result={result!r}")
    except NullRunBlockedException as exc:
        # BLOCK path — span_end and audit_events landed in the
        # backend; no cost_events row exists for this call. Print
        # the wire-level error_code (e.g. NR-T001 / TOOL_BLOCKED)
        # and the first-class reason for the kill.
        print(
            f"[nullrun] tool={name} decision=block "
            f"code={exc.error_code} reason={exc.reason[:120]}"
        )
    except NullRunError as exc:
        # Anything else from the SDK family: backend down, auth
        # rejected, transport error. Print code + message so the
        # dashboard URL reflects a single failure mode.
        print(
            f"[nullrun] tool={name} decision=error "
            f"code={exc.error_code} msg={str(exc)[:120]}"
        )
    finally:
        set_call_context(tools=[])


if __name__ == "__main__":
    tools = sys.argv[1:] or DEFAULT_TOOLS
    try:
        for name in tools:
            probe(name)
    finally:
        shutdown()
