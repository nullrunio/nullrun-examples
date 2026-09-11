"""Probe for TC-8 — chain heartbeat (TTL extension via ping_chain)."""
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

if len(sys.argv) >= 2 and not os.environ.get("NULLRUN_API_KEY"):
    os.environ["NULLRUN_API_KEY"] = sys.argv[1]

from nullrun import chain, init_or_die, shutdown  # noqa: E402
from nullrun.context import set_call_context  # noqa: E402

init_or_die()


def main() -> int:
    from nullrun import get_runtime
    rt = get_runtime()
    chain_id = str(uuid.uuid4())
    print(f"chain_id={chain_id}", flush=True)

    set_call_context(model="gpt-4o-mini", tools=("read_file",))

    with chain(chain_id, op="start"):
        # Open chain via initial /gate
        try:
            rt.check_workflow_budget()
            print("GATE_OK", flush=True)
        except Exception as e:
            print(f"GATE_FAIL: {type(e).__name__}: {e}", flush=True)
            shutdown()
            return 0

        # Heartbeat 3 times via direct transport call (private API; the
        # public ``Runtime.heartbeat`` does not exist — see WS-03 finding
        # in the prod-ready checklist).
        for i in range(3):
            try:
                result = rt._transport.heartbeat(chain_id)
                print(f"HEARTBEAT[{i}]: {result}", flush=True)
            except Exception as e:
                print(f"HEARTBEAT[{i}]: {type(e).__name__}: {e}", flush=True)
            time.sleep(0.5)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
