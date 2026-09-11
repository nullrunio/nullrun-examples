"""Probe for TC-11 — /execute direct allow (non-sensitive tool)."""
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
    from nullrun.context import set_call_context
    rt = get_runtime()

    set_call_context(model="gpt-4o-mini", tools=("read_file",))

    # Step 1: /gate via public check_workflow_budget — auto-fills org_id
    try:
        rt.check_workflow_budget()
        print("GATE_OK", flush=True)
    except Exception as e:
        print(f"GATE_FAIL: {type(e).__name__}: {e}", flush=True)

    # Step 2: /execute — public runtime.execute (auto-fills org_id+trace_id)
    # Should use the execution_id captured from /gate via contextvar
    try:
        result = rt.execute(
            tool_name="read_file",
            input_data={"path": "/tmp/test.txt"},
            mode="auto",
        )
        print(f"EXECUTE_OK={result}", flush=True)
        decision = result.get("decision") or result.get("verdict") or result.get("allowed")
        print(f"EXECUTE_DECISION={decision}", flush=True)
    except Exception as e:
        print(f"EXECUTE_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
