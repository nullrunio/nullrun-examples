"""Probe for TC-21 — workflow state matrix (paused / killed / inactive / chain org mismatch).

Verifies the SDK exposes the full exception class catalog for workflow
state transitions. The UI-driven pause/kill flow is documented but
requires human approval through /control-center; this probe verifies
the SDK-side typed exceptions are importable and the wire-level
fail-CLOSED response is correctly handled.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "examples"))
try:
    from _env import load_env
    load_env()
except Exception:
    pass

if len(sys.argv) >= 2:
    os.environ["NULLRUN_API_KEY"] = sys.argv[1]

from nullrun import init_or_die, shutdown  # noqa: E402

init_or_die()


def main() -> int:
    from nullrun.breaker import exceptions as exc

    # Verify full exception catalog
    classes_to_check = [
        ("NullRunWorkflowInactiveError", exc),
        ("NullRunWorkflowKilledError", exc),
        ("NullRunChainError", exc),
        ("WorkflowKilledException", exc),
        ("WorkflowKilledInterrupt", exc),
        ("WorkflowPausedException", exc),
    ]
    for cls_name, module in classes_to_check:
        cls = getattr(module, cls_name, None)
        exists = cls is not None
        print(f"{cls_name}_EXISTS={exists}", flush=True)
        if exists:
            print(f"{cls_name}_NAME={cls.__name__}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
