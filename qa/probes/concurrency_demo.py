"""Probe for TC-27 — concurrency: 10 sequential /gate calls, verify reservation tracking."""
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

    # 10 sequential /gate calls, each with unique operation_id
    reservation_ids = []
    decisions = []
    for i in range(10):
        op_id = f"tc27-conc-{i}-{uuid.uuid4()}"
        try:
            r = rt._transport.check(check_request={
                "mode": "check",
                "tools": ("read_file",),
                "organization_id": rt.organization_id,
                "execution_id": str(uuid.uuid4()),
                "operation_id": op_id,
                "action_digest": f"tc27-conc-{i}",
                "estimated_tokens": 1,
            })
            reservation_ids.append(r.get("reservation_id") or r.get("execution_id"))
            decisions.append(r.get("decision", "unknown"))
            print(f"CONC_{i}=decision:{r.get('decision')}", flush=True)
        except Exception as e:
            print(f"CONC_{i}_FAIL: {type(e).__name__}: {e}", flush=True)
            decisions.append("error")

    # All reservation_ids should be unique (no double-mint)
    unique_ids = set(reservation_ids) - {None}
    print(f"UNIQUE_RESERVATIONS={len(unique_ids)}/{len(reservation_ids)}", flush=True)
    print(f"DECISION_SUMMARY={dict((d, decisions.count(d)) for d in set(decisions))}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
