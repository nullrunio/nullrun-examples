"""Shared example plumbing.

The :func:`example_run` helper folds ``.env`` loading, init, and
shutdown into one context manager. The actual work (build the
client, decorate the function, run it) stays in the example so the
diff between "with" and "without NullRun" remains visible to a
first-time reader.

Typical use:

    from _boilerplate import example_run
    with example_run() as run:
        run(answer, "In one sentence, what does NullRun do?")
"""
from __future__ import annotations

import contextlib
import os
import time
from typing import Iterator

from _env import load_env

from nullrun import init_or_die, shutdown


@contextlib.contextmanager
def example_run(api_key: str | None = None, api_url: str | None = None) -> Iterator[None]:
    """Bootstrap ``.env`` + ``init_or_die`` and tear down with ``shutdown``.

    Args:
        api_key: Override ``NULLRUN_API_KEY`` (mostly for tests). Defaults
            to whatever ``examples/.env`` or the shell environment supplies.
        api_url: Override ``NULLRUN_API_URL`` similarly.

    Yields:
        None — examples just ``print()`` the result of the call they
        invoke inside the block.

    Notes:
        * ``init_or_die()`` exits with the four-line developer report if
          ``NULLRUN_API_KEY`` is missing.
        * ``shutdown()`` sends a clean WebSocket close frame. No-op if
          the runtime was never created, so it is safe in ``finally``.
        * ``WorkflowKilledInterrupt`` is not swallowed here — kill must
          reach the top of the agent loop. ``with nullrun.handle():``
          around the inner call is still the right wrapper.
    """
    load_env()
    if api_key is not None:
        os.environ["NULLRUN_API_KEY"] = api_key
    if api_url is not None:
        os.environ["NULLRUN_API_URL"] = api_url
    init_or_die()
    try:
        yield
    finally:
        shutdown()


__all__ = ["example_run", "init_sdk_or_die", "RUN_ID"]


# ---------------------------------------------------------------------------
# Convenience helpers for SDK test plans (used by SDK_TEST.md §7.5/§7.6 scripts).
# ---------------------------------------------------------------------------


RUN_ID = os.environ.get("NULLRUN_RUN_ID", time.strftime("%Y%m%dT%H%M"))


def init_sdk_or_die() -> None:
    """Load .env + init SDK; exits if ``NULLRUN_API_KEY`` missing.

    Test-plan helper. Most examples should prefer :func:`example_run`
    over calling this directly.
    """
    load_env()
    init_or_die()
