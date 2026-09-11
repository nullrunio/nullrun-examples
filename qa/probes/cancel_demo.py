"""Probe for TC-7 — in-flight execution cancel via /api/v1/cancel.

Opens chain, triggers a /gate that mints execution_id, captures the
server-minted execution_id, then explicitly cancels it via rt.cancel_execution.

Wire dump captures: /auth/verify, /gate (allow), /cancel.
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

if len(sys.argv) >= 2 and not os.environ.get("NULLRUN_API_KEY"):
    os.environ["NULLRUN_API_KEY"] = sys.argv[1]

from nullrun import chain, init_or_die, shutdown  # noqa: E402
from nullrun.context import set_call_context  # noqa: E402

init_or_die()


def main() -> int:
    from nullrun import get_runtime
    rt = get_runtime()

    # Step 1: Open chain + trigger /gate via check_workflow_budget.
    # That call mints a server execution_id we can cancel.
    chain_id = str(uuid.uuid4())
    print(f"chain_id={chain_id}", flush=True)

    with chain(chain_id, op="start"):
        # Safe tool — won't be blocked
        set_call_context(model="gpt-4o-mini", tools=("read_file",))
        try:
            rt.check_workflow_budget()
            print("GATE_OK", flush=True)
        except Exception as e:
            print(f"GATE_FAIL: {type(e).__name__}: {e}", flush=True)
            shutdown()
            return 0

        # Capture the server-minted execution_id from context
        from nullrun.context import get_server_minted_execution_id
        exec_id = get_server_minted_execution_id()
        print(f"SERVER_EXEC_ID={exec_id}", flush=True)

        # Step 2: Cancel the execution mid-chain
        try:
            result = rt.cancel_execution(exec_id, reason="tc-7 cancellation test")
            print(f"CANCEL_RESULT={result}", flush=True)
        except Exception as e:
            print(f"CANCEL_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
