"""Probe for TC-30 — SDK lifecycle: init → shutdown → re-init round-trip."""
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

from nullrun.runtime import NullRunRuntime  # noqa: E402


def main() -> int:
    from nullrun import init_or_die, shutdown
    from nullrun.context import set_call_context

    # Lifecycle stage 1: first init
    init_or_die()
    from nullrun import get_runtime
    rt1 = get_runtime()
    org1 = rt1.organization_id
    print(f"LIFECYCLE_INIT_1 org={org1}", flush=True)

    # Stage 2: use runtime
    set_call_context(model="gpt-4o-mini", tools=("read_file",))
    try:
        rt1.check_workflow_budget()
        print("LIFECYCLE_GATE_1_OK", flush=True)
    except Exception as e:
        print(f"LIFECYCLE_GATE_1_FAIL: {type(e).__name__}: {e}", flush=True)

    # Stage 3: shutdown
    shutdown()
    print("LIFECYCLE_SHUTDOWN_OK", flush=True)

    # Stage 4: re-init (should work after shutdown)
    init_or_die()
    rt2 = get_runtime()
    org2 = rt2.organization_id
    print(f"LIFECYCLE_INIT_2 org={org2}", flush=True)

    # Stage 5: verify same singleton is reused
    same_org = org1 == org2
    print(f"LIFECYCLE_ORG_MATCH={same_org}", flush=True)

    # Stage 6: use re-init runtime
    try:
        rt2.check_workflow_budget()
        print("LIFECYCLE_GATE_2_OK", flush=True)
    except Exception as e:
        print(f"LIFECYCLE_GATE_2_FAIL: {type(e).__name__}: {e}", flush=True)

    # Stage 7: reset singleton + re-init from scratch
    NullRunRuntime.reset_instance()
    init_or_die()
    rt3 = get_runtime()
    print(f"LIFECYCLE_RESET_ORG={rt3.organization_id}", flush=True)

    shutdown()
    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
