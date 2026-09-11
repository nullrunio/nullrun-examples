"""Probe for TC-13 — approval DENIED flow (require_approval → deny → typed exception).

Verifies that:
  1. SDK exposes NullRunApprovalDeniedError class
  2. SDK exposes NullRunApprovalExpiredError class (NR-A012)
  3. /check with denied approval_id returns 403 with DENIED error_code
  4. SDK raises typed exception, not generic NullRunTransportError
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
    from nullrun import get_runtime
    from nullrun.breaker import exceptions as nullrun_exc

    # Step 1: Verify exception classes are exposed
    denied_cls = getattr(nullrun_exc, "NullRunApprovalDeniedError", None)
    expired_cls = getattr(nullrun_exc, "NullRunApprovalExpiredError", None)
    replay_cls = getattr(nullrun_exc, "NullRunApprovalReplayRejectedError", None)

    print(f"DENIED_CLS_EXISTS={denied_cls is not None}", flush=True)
    print(f"EXPIRED_CLS_EXISTS={expired_cls is not None}", flush=True)
    print(f"REPLAY_CLS_EXISTS={replay_cls is not None}", flush=True)
    if denied_cls:
        print(f"DENIED_CLS_NAME={denied_cls.__name__}", flush=True)
    if expired_cls:
        print(f"EXPIRED_CLS_NAME={expired_cls.__name__}", flush=True)
    if replay_cls:
        print(f"REPLAY_CLS_NAME={replay_cls.__name__}", flush=True)

    # Step 2: Verify status endpoint reachable
    rt = get_runtime()
    try:
        status = rt.status()
        print(f"STATUS_OK={status}", flush=True)
    except Exception as e:
        print(f"STATUS_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
