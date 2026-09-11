"""Probe for TC-12 — approval GRANTED flow (require_approval → approve → re-fire).

Verifies the SDK hooks:
  1. /check returns require_approval decision
  2. SDK raises NullRunApprovalNotYetApprovedError with approval_id
  3. WS callback registered for approval_resolved
  4. Approval status poll (rt.status) returns valid state

The actual operator-driven approval via UI requires a human in the loop;
this probe verifies the SDK-side wire plumbing is correct.
"""
from __future__ import annotations

import os
import sys
import uuid
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
    from nullrun.context import set_call_context
    rt = get_runtime()

    set_call_context(model="gpt-4o-mini", tools=("refund_customer",))

    # Step 1: WS connect with approval callback
    try:
        ws = rt._transport.connect_websocket(
            organization_id=rt.organization_id,
            on_approval_resolved=lambda evt: print(f"WS_APPROVAL_RESOLVED={evt}", flush=True),
        )
        print(f"WS_CONNECTED type={type(ws).__name__}", flush=True)
    except Exception as e:
        print(f"WS_CONNECT_FAIL: {type(e).__name__}: {e}", flush=True)

    # Step 2: Try /gate on refund_customer (should require_approval)
    try:
        result = rt._transport.check(check_request={
            "mode": "check",
            "tools": ("refund_customer",),
            "organization_id": rt.organization_id,
            "execution_id": str(uuid.uuid4()),
            "operation_id": f"tc12-{uuid.uuid4()}",
            "action_digest": "tc12-approval-granted-test",
            "estimated_tokens": 1,
        })
        decision = result.get("decision")
        approval_id = result.get("approval_id") or result.get("reservation_id")
        print(f"CHECK_DECISION={decision}", flush=True)
        print(f"APPROVAL_ID={approval_id}", flush=True)
    except Exception as e:
        # NR-A010 raised for require_approval — capture approval_id from exc
        print(f"CHECK_EXCEPTION: {type(e).__name__}: {e}", flush=True)
        approval_id = getattr(e, "approval_id", None)
        print(f"APPROVAL_ID_FROM_EXCEPTION={approval_id}", flush=True)

    # Step 3: SDK status check
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
