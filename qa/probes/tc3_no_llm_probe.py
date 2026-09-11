"""TC-3 no-LLM probe: drives check_workflow_budget() + synthetic track()
events with cost_cents above the policy's budget_cents cap to force a
budget-block on the /track path.

Key insight (verified 2026-09-10):
  /gate only evaluates tool_block / rate_limit / approval paths.
  Budget is enforced at /track. So TC-3 (block via budget) MUST
  drive /track, not just /gate.

Why synthetic track() (not @protect):
  @protect's track_tool derives cost from duration_ms + policy, which
  is 0 for a stub returning instantly. We need a real cost value to
  push the cumulative counter over the budget_cents cap.
  runtime.track(event) takes cost_cents directly and is the
  load-bearing surface for cost_events ingestion.

Probe structure:
  - 3 iterations: check_workflow_budget() then runtime.track(cost=10)
  - cost_cents=10 per track; budget_cents=1 from policy → first
    track exceeds budget → block.
  - Each iteration appends ('allow'|'block', i, type, code)
  - Print `---PROBE-RESULTS---` then one tuple per call
"""
from __future__ import annotations
import sys, pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env  # noqa: E402

load_env()


from nullrun import init_or_die, shutdown, set_call_context  # noqa: E402
from nullrun import get_runtime  # noqa: E402

init_or_die()
runtime = get_runtime()

# Provide a tools context so /gate's tool_block rule (which has
# reason="no_tools_field" as a default-block in this org) does not
# pre-empt the budget test.
set_call_context(tools=["read_file"])

results = []
try:
    for i in range(10):
        # 1. Gate pre-flight (should allow when budget has capacity)
        try:
            runtime.check_workflow_budget()
        except BaseException as e:
            code = getattr(e, "error_code", None) or getattr(e, "code", None)
            results.append(("block", i, type(e).__name__, code))
            break
        # 2. Synthetic /track with large token count so the backend
        #    computes a cost well above the 1¢ budget cap.
        #    cost_cents is STRIPPED from the wire (per
        #    transport.py:1930-1934) — tokens is the only knob that
        #    drives the authoritative cost.
        try:
            event = {
                "type": "tool_call",
                "tool_name": "read_file",
                "tokens": 1_000_000,
                "model": "gpt-4o-mini",
            }
            runtime.track(event)
            results.append(("allow", i, None, None))
        except BaseException as e:
            code = getattr(e, "error_code", None) or getattr(e, "code", None)
            results.append(("block", i, type(e).__name__, code))
            break
finally:
    set_call_context(tools=[])
    shutdown()

print("---PROBE-RESULTS---")
for r in results:
    print(r)
