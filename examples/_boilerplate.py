"""Shared example plumbing.

The patterns in this module exist so each example file can stay under
the 80-line ceiling called out in the top-level README. Every basic
example does the same five things:

    1. Load ``examples/.env`` into ``os.environ``.
    2. (Optional) call ``init_or_die()`` so a missing ``NULLRUN_API_KEY``
       exits cleanly. SDK 0.18.1+: this step is optional — the first
       ``@protect`` call lazy-creates the runtime from the env var, so
       most examples now skip it and rely on the ``with nullrun.handle():``
       block to print the structured four-line developer report if the
       key is missing.
    3. Wrap the call site with a gate (``@protect``) — and optionally a
       friendly-exit wrapper (``with nullrun.handle():`` / ``@guarded``).
    4. Run one ``@protect``-decorated call.
    5. ``shutdown()`` in a ``finally`` block to send a clean WS close.

The :func:`example_run` helper folds steps 1, 2 and 5 into a single
context manager. The actual work (build the client, decorate the
function, run it) stays in the example so the diff between "with" and
"without NullRun" remains visible to a first-time reader.

Typical use:

    from _boilerplate import example_run
    with example_run() as run:
        run(answer, "In one sentence, what does NullRun do?")
"""
from __future__ import annotations

import contextlib
from typing import Any, Callable, Iterator

from _env import load_env

import nullrun
from nullrun import init_or_die, shutdown


@contextlib.contextmanager
def example_run(api_key: str | None = None, api_url: str | None = None) -> Iterator[None]:
    """Bootstrap ``.env`` + ``init_or_die`` and tear down with ``shutdown``.

    Args:
        api_key: Override ``NULLRUN_API_KEY`` (mostly for tests). Defaults
            to whatever ``examples/.env`` or the shell environment
            supplies via ``init_or_die()``.
        api_url: Override ``NULLRUN_API_URL`` similarly.

    Yields:
        None — examples just ``print()`` the result of the call they
        invoke inside the block.

    Notes:
        * ``init_or_die()`` exits with the four-line developer report if
          ``NULLRUN_API_KEY`` is missing. No try/except needed in the
          example body. New examples (SDK 0.18.1+) can skip this step
          entirely and let the first ``@protect`` call lazy-init — the
          trade-off is the missing-key error surfaces at the gate call,
          not at module load time.
        * ``shutdown()`` sends a clean WebSocket close frame so the
          backend does not log ``"Connection reset without closing
          handshake"``. No-op if the runtime was never created (which
          is why it's safe to put in ``finally``).
        * ``WorkflowKilledInterrupt`` (a ``NullRunError`` subclass) is
          NOT swallowed here — kill must reach the top of the agent
          loop. ``with nullrun.handle():`` is still the right context
          manager around the inner call (it re-raises kill explicitly).
    """
    load_env()
    if api_key is not None:
        import os
        os.environ["NULLRUN_API_KEY"] = api_key
    if api_url is not None:
        import os
        os.environ["NULLRUN_API_URL"] = api_url
    init_or_die()
    try:
        yield
    finally:
        shutdown()


__all__ = ["example_run", "init_sdk_or_die", "RUN_ID"]


# ---------------------------------------------------------------------------
# Convenience helpers for SDK test plans (used by SDK_TEST.md §7.5/§7.6 scripts).
# These are intentionally minimal wrappers — full setup (workflow isolation,
# pre-flight) lives in the test runner, not in examples.
# ---------------------------------------------------------------------------
import os as _os
import time as _time


RUN_ID = _os.environ.get("NULLRUN_RUN_ID", _time.strftime("%Y%m%dT%H%M"))


def init_sdk_or_die() -> None:
    """Load .env + init SDK; exits if NULLRUN_API_KEY missing.

    Test-plan helper. Most examples should prefer :func:`example_run`
    (or no init at all, since 0.18.1) over calling this directly.
    """
    load_env()
    try:
        import nullrun
        nullrun.init_or_die()
    except Exception as exc:  # noqa: BLE001
        print(f"[init_sdk_or_die] SDK init failed: {type(exc).__name__}: {exc}")
        raise
