"""Minimal ToolBlock gate pre-flight probe.

Calls ``/api/v1/gate`` once per tool name with ``check_type="tool"`` and
prints the decision. No LLM, no LangChain — just the gate.

The probe runs without ``with workflow()`` so the API key's bound
workflow_id is used; the SDK resolves it automatically on the
first ``check_workflow_budget`` call. Per-key tool blocking in
the dashboard blocks here; workflow-scoped blocks would too.

ToolBlock pattern semantics (verified 2026-07-XX against
``backend/src/proxy/http/gate/internal.rs::glob_match``):

  * Single-`*` glob with optional `|` alternation.
  * `*` matches any prefix/suffix; `.` is a literal dot.
  * `bash`           → exact-match ``bash`` only.
  * `bash*`          → blocks ``bash``, ``bash_run``, ``bash.foo``.
  * `bash.*`         → blocks ``bash`` (bare) AND ``bash.foo`` /
                       ``bash.foo.bar`` (smart prefix match — closes
                       the templates gap where exact names used to
                       slip past ``bash.*``).
  * `*.drop_*`       → blocks ``db.drop_users``, ``db.drop_all`` …
  * `bash|sh|shell`  → blocks any of the three (alternation).
  * `bash.*|sh.*`    → combines smart prefix + alternation.

The dashboard hint copy now reflects this — older screenshots may
still show ``RE2 regex`` wording, which was misleading.

Run:
    pip install nullrun
    export NULLRUN_API_KEY=nr_live_...
    python examples/gate_check_demo.py [tool_name_1 tool_name_2 ...]

Defaults probe ``["bash", "read_file", "filesystem.delete_user"]`` so
you see both an allow (no rule) and a block (rule match) without
editing the file.
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import asyncio
import contextlib
import os
import sys
import threading

from nullrun import init_or_die, set_call_context, shutdown

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing


@contextlib.contextmanager
def _silent_cancelled_in_daemon():
    """Suppress asyncio.CancelledError noise from background daemon threads.

    Installs a scoped ``threading.excepthook`` override for the duration of
    the block; restores the previous hook on exit. Avoids leaking the
    override into other examples if this file is ever imported.
    """
    previous = threading.excepthook

    def _hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is asyncio.CancelledError:
            return
        previous(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = _hook
    try:
        yield
    finally:
        threading.excepthook = previous


DEFAULT_TOOLS = ["bash", "bash.foo", "sh", "shell", "shell.foo", "read_file", "filesystem.delete_user"]


def probe(tool_name: str) -> None:
    """Run a single /gate pre-flight for ``tool_name`` and print the result.

    Uses ``set_call_context(tools=[...])`` to attach the tool list to the
    next ``check_workflow_budget`` call (T4 in the SDK). The backend's
    ``gate/internal.rs::check_tool_block`` matches each name against the
    workflow's blocked_tools aggregate and returns block on any match.
    """
    set_call_context(tools=[tool_name])
    try:
        from nullrun import get_runtime
        from nullrun.breaker.exceptions import WorkflowKilledInterrupt

        runtime = get_runtime()
        try:
            runtime.check_workflow_budget()
            print(f"[nullrun] tool={tool_name} decision=allow")
        except WorkflowKilledInterrupt as exc:
            print(
                f"[nullrun] tool={tool_name} decision=block "
                f"exc_type={type(exc).__name__} exc={exc!r}"
            )
    finally:
        # Clear so the next iteration starts from a clean slate.
        set_call_context(tools=[])


if __name__ == "__main__":
    tools = sys.argv[1:] or DEFAULT_TOOLS
    try:
        # The SDK resolves the workflow_id from the API key's
        # bound workflow, so no ``with workflow()`` block is needed.
        with _silent_cancelled_in_daemon():
            for name in tools:
                probe(name)
    finally:
        shutdown()