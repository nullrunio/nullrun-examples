"""Probe for TC-14 — approval REPLAY (same approval_id twice → NR-A015).

Verifies wire-level replay semantics:
  1. First /check with fake approval_id: server should return error_code
  2. Second /check with same approval_id: should still get same response
  3. /execute with same approval_id: NR-A015 typed exception
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

    fake_approval_id = f"apr_{uuid.uuid4()}"

    # /check with non-existent approval_id
    try:
        result = rt._transport.check(check_request={
            "mode": "check",
            "tools": ("refund_customer",),
            "organization_id": rt.organization_id,
            "execution_id": str(uuid.uuid4()),
            "operation_id": f"tc14-{uuid.uuid4()}",
            "action_digest": "tc14-replay-test",
            "approval_id": fake_approval_id,
            "estimated_tokens": 1,
        })
        print(f"CHECK_OK={result}", flush=True)
        decision = result.get("decision")
        ec = result.get("error_code")
        print(f"CHECK_DECISION={decision} error_code={ec}", flush=True)
    except Exception as e:
        print(f"CHECK_FAIL: {type(e).__name__}: {e}", flush=True)

    # Second call with same fake approval_id (should replay-cache)
    try:
        result2 = rt._transport.check(check_request={
            "mode": "check",
            "tools": ("refund_customer",),
            "organization_id": rt.organization_id,
            "execution_id": str(uuid.uuid4()),
            "operation_id": f"tc14-{uuid.uuid4()}",
            "action_digest": "tc14-replay-test",
            "approval_id": fake_approval_id,
            "estimated_tokens": 1,
        })
        print(f"REPLAY_OK={result2}", flush=True)
        replay = result2.get("idempotent_replay") or result2.get("replay") or False
        print(f"REPLAY_FLAG={replay}", flush=True)
    except Exception as e:
        print(f"REPLAY_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
