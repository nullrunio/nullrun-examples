"""Minimal ToolBlock gate pre-flight probe.

Calls ``/api/v1/gate`` once per tool name and prints the decision.
No LLM, no LangChain — just the gate.

The probe runs without ``with workflow()`` so the API key's bound
workflow_id is used; the SDK resolves it automatically on the
first ``@nullrun.protect`` call. Per-key tool blocking in the
dashboard blocks here; workflow-scoped blocks would too.

This demo is the user-spirit canonical pattern: each tool gets a
zero-arg function decorated with ``@nullrun.protect``. The SDK's
F03 fix auto-populates ``tools=[fn.__name__]`` from the function
name, so the wire ``tools`` value matches the CLI arg without the
caller having to know about ``set_call_context``. Each top-level
invocation mints a fresh ``operation_id`` via the decorator's
contextvar hoist (P0-27 fix), so back-to-back retries never collide
on the same idempotency key.

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
import sys
import threading

import nullrun
from nullrun import shutdown


@contextlib.contextmanager
def _silent_cancelled_in_daemon():
    """Suppress asyncio.CancelledError noise from the SDK's background WS thread.

    SDK-internal: the SDK spins up a daemon thread for the WebSocket control
    plane (``nullrun.observability.ws.WsControlPlane._reader_loop`` and the
    ping keep-alive) that cancels its own ``asyncio.Task``s on shutdown.
    Python's default ``threading.excepthook`` prints
    ``Exception ignored in: <coroutine ...>`` for every cancelled task,
    which is informational-only noise for end users. This scoped hook
    silences ONLY ``asyncio.CancelledError`` from those daemon threads
    and restores the previous hook on exit.

    Do NOT use this as general-purpose ``asyncio.CancelledError``
    suppression — if your own code raises ``CancelledError``, you want
    to see the traceback. Scope is narrow on purpose.
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


def _make_probe(tool_name: str):
    """Build a ``@nullrun.protect``-wrapped zero-arg probe whose
    ``__name__`` matches ``tool_name``.

    Why this is the user-spirit canonical pattern (2026-09-11
    IDEM-01 blast-radius retest):

      * End users adding ``@nullrun.protect`` to a tool-call
        function should NOT have to know about ``set_call_context``,
        ``operation_id`` minting, or contextvar hoists — the SDK
        handles all three.

      * The SDK's F03 fix (decorators.py around lines 504-525 of
        ``nullrun-sdk-python``) populates
        ``_call_tools_var = (fn.__name__,)`` automatically when the
        user did NOT call ``set_call_context(tools=...)``. This is
        what wires ``tools=[fn.__name__]`` onto the gate payload
        without any explicit user-side glue.

      * Each top-level invocation mints a fresh ``operation_id``
        via the decorator's contextvar hoist (P0-27), so a TC-1
        loop across multiple tools never reuses the same
        idempotency key. This is exactly the user-spirit invariant
        the @protect() decorator is designed to provide.

    The trick: rename ``probe.__name__`` BEFORE wrapping so the
    decorator's F03 capture reads the CLI-passed tool name. After
    decoration ``fn.__name__`` is the wire ``tools`` value, so the
    dashboard's tool-block policy matches on the same string the
    caller asked for.
    """
    def probe() -> None:
        # Empty body — the decorator's pre-execution gate has
        # already evaluated the tool-block policy by the time
        # we get here. If the gate blocks, the decorator raises
        # ``NullRunBlockedException`` BEFORE this body runs.
        return None

    probe.__name__ = tool_name
    return nullrun.protect(probe)


def _probe(tool_name: str) -> None:
    """Run a single /gate pre-flight for ``tool_name`` and print the result."""
    probe = _make_probe(tool_name)
    try:
        probe()
        print(f"[nullrun] tool={tool_name} decision=allow")
    except nullrun.NullRunBlockedException as exc:
        print(
            f"[nullrun] tool={tool_name} decision=block "
            f"exc_type={type(exc).__name__} exc={exc!r}"
        )


if __name__ == "__main__":
    tools = sys.argv[1:] or DEFAULT_TOOLS
    try:
        # The SDK resolves the workflow_id from the API key's
        # bound workflow, so no ``with workflow()`` block is needed.
        with _silent_cancelled_in_daemon():
            for name in tools:
                _probe(name)
    finally:
        shutdown()
