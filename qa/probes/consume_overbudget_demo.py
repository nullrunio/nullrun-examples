"""Probe for TC-15 — consume > reserve + ε → CONSUME_OVERBUDGET 422.

Strategy: reserve small (1c) then consume large via direct /track with cost_cents.
Default ε=1c, so 100c over reserve should trigger CONSUME_OVERBUDGET.

Note: synthetic 1¢ policy on this org blocks /gate, so we use the
prior /gate reservation from a different TC to mint a fresh
reservation_id, then test /track over-budget on it.
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

    set_call_context(model="gpt-4o-mini", tools=("read_file",))

    # Step 1: /gate to mint execution_id (reserve 1c)
    try:
        gate_result = rt._transport.check(check_request={
            "mode": "check",
            "tools": ("read_file",),
            "organization_id": rt.organization_id,
            "execution_id": str(uuid.uuid4()),
            "operation_id": f"tc15-{uuid.uuid4()}",
            "action_digest": "tc15-overbudget-test",
            "estimated_tokens": 1,
        })
        reservation_id = gate_result.get("reservation_id") or gate_result.get("execution_id")
        print(f"GATE_OK reservation_id={reservation_id}", flush=True)
        if not reservation_id:
            print("GATE_NO_RESERVATION", flush=True)
            shutdown()
            return 0
    except Exception as e:
        print(f"GATE_FAIL: {type(e).__name__}: {e}", flush=True)
        shutdown()
        return 0

    # Step 2: /track with cost_cents >> reserve (over budget)
    try:
        result = rt._transport.track_single(request={
            "reservation_id": reservation_id,
            "workflow_id": rt.workflow_id,
            "tokens": 1000000,  # 1M tokens → very large cost
            "cost_cents": 999999,  # way over reserve
            "cost_source": "provisional",
            "model": "gpt-4o-mini",
        })
        print(f"TRACK_OK={result}", flush=True)
    except Exception as e:
        # Expected: NullRunConsumeOverbudgetError with CONSUME_OVERBUDGET
        print(f"TRACK_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
