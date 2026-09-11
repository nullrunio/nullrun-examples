"""Smoke check: verify SDK /check (via check_workflow_budget) works with current API key.
Used by TS-12e load tests as setup validation.
"""
from __future__ import annotations
import sys, pathlib, os, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from examples._env import load_env
load_env()

import nullrun
from nullrun import init_or_die, shutdown, get_runtime

# Init with workflow_id of test workflow
nullrun.init(
    workflow_id="2af6d075-7ce0-4f7e-b3b5-55c714431dff",
)

runtime = get_runtime()

try:
    # Try a check_workflow_budget - should return execution_id
    result = runtime.check_workflow_budget(
        tool="bash",
        estimated_tokens=100,
    )
    print(f"OK smoke-check passed; result type={type(result).__name__}")
    print(f"  result: {result}")
except Exception as e:
    print(f"FAIL smoke-check: {type(e).__name__}: {str(e)[:300]}")
    import traceback
    traceback.print_exc()
finally:
    shutdown()
