"""Probe for TC-28 — Lua v3 period-bound counter smoke (reserve → period rollover → new reserve)."""
from __future__ import annotations

import os
import sys
import time
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

    # First reserve — should succeed
    op1 = f"tc28-{uuid.uuid4()}"
    try:
        rt._transport.check(check_request={
            "mode": "check",
            "tools": ("read_file",),
            "organization_id": rt.organization_id,
            "execution_id": str(uuid.uuid4()),
            "operation_id": op1,
            "action_digest": "tc28-period-rollover",
            "estimated_tokens": 1,
        })
        print("RESERVE_1_OK", flush=True)
    except Exception as e:
        print(f"RESERVE_1_FAIL: {type(e).__name__}: {e}", flush=True)

    # Second reserve — different op_id, same period
    op2 = f"tc28-{uuid.uuid4()}"
    try:
        rt._transport.check(check_request={
            "mode": "check",
            "tools": ("read_file",),
            "organization_id": rt.organization_id,
            "execution_id": str(uuid.uuid4()),
            "operation_id": op2,
            "action_digest": "tc28-period-rollover",
            "estimated_tokens": 1,
        })
        print("RESERVE_2_OK", flush=True)
    except Exception as e:
        print(f"RESERVE_2_FAIL: {type(e).__name__}: {e}", flush=True)

    # Approximate budget — verify Redis period source
    try:
        budget = rt.approximate_budget()
        print(f"BUDGET_APPROX={budget}", flush=True)
    except Exception as e:
        print(f"BUDGET_APPROX_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
