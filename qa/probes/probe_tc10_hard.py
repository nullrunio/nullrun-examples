"""TC-SDK-010 probe: single /check against workflow with hard budget $1.

With workflow budget=100¢ ($1) and current spend ~778¢, the first /check
should block with BUDGET_HARD_BLOCKED. Tests enforcement path WITHOUT
real LLM (uses runtime.check_workflow_budget() directly).

Per LATEST_PLAN §5 TC-SDK-010 wire schema:
  {"exception": "NullRunBudgetError", "error_code": "BUDGET_HARD_BLOCKED",
   "status_code": 402, "details": {"current_spend_cents": ">= 100",
   "budget_cents": 100, "rule_kind": "workflow_budget_exceeded"}}
"""
from __future__ import annotations
import sys, pathlib, json
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import time
from nullrun import init_or_die, shutdown, get_runtime
from nullrun.breaker.exceptions import WorkflowKilledInterrupt

init_or_die()
runtime = get_runtime()

start = time.monotonic()
try:
    runtime.check_workflow_budget()
    elapsed = time.monotonic() - start
    print(f"[TC-SDK-010] t={elapsed:.3f}s UNEXPECTED_ALLOW")
except WorkflowKilledInterrupt as exc:
    elapsed = time.monotonic() - start
    code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
    details = getattr(exc, "details", None)
    print(f"[TC-SDK-010] t={elapsed:.3f}s BLOCK code={code}")
    print(f"[TC-SDK-010] msg={str(exc)[:300]!r}")
    print(f"[TC-SDK-010] details={json.dumps(details, default=str) if details else None}")
except Exception as e:
    elapsed = time.monotonic() - start
    code = getattr(e, "code", None) or getattr(e, "error_code", None)
    print(f"[TC-SDK-010] t={elapsed:.3f}s OTHER-EXC type={type(e).__name__} code={code} msg={str(e)[:300]!r}")
finally:
    shutdown()