"""TC-SDK-011 probe: soft budget with active chain (no LLM).

Tests that within an active chain(), the soft budget policy allows
requests even when current spend exceeds the budget, up to the
overdraft cap. Without chain, would block with BUDGET_SOFT_BLOCKED.

Per LATEST_PLAN §5 TC-SDK-011 wire schema:
  Pass: {"status_code": 200, "execution_id": "<uuid-v7>",
         "chain_state": "ACTIVE", "overdraft_used_cents": ">= 0"}
  Fail (overdraft cap exceeded): {"exception": "NullRunBudgetError",
         "error_code": "BUDGET_OVERDRAFT_EXCEEDED", "status_code": 402}
"""
from __future__ import annotations
import sys, pathlib, json
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import time, uuid
from nullrun import init_or_die, shutdown, get_runtime, chain
from nullrun.breaker.exceptions import WorkflowKilledInterrupt

init_or_die()
runtime = get_runtime()

chain_id = str(uuid.uuid4())
print(f"[TC-SDK-011] chain_id={chain_id}")
print(f"[TC-SDK-011] Starting chain context...")

start = time.monotonic()
try:
    with chain(chain_id, op="start"):
        # Test 1: First check (should be allowed via chain, may overdraft)
        try:
            result = runtime.check_workflow_budget()
            elapsed = time.monotonic() - start
            print(f"[TC-SDK-011] TEST 1: ALLOW (within overdraft)")
            print(f"  elapsed={elapsed:.3f}s result_type={type(result).__name__}")
        except WorkflowKilledInterrupt as exc:
            elapsed = time.monotonic() - start
            code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
            print(f"[TC-SDK-011] TEST 1: BLOCK code={code}")
            print(f"  msg={str(exc)[:300]!r}")
            print(f"  details={getattr(exc, 'details', None)}")
finally:
    shutdown()