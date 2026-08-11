"""Probe for BUD below-threshold verification WITHOUT LLM calls.
Uses runtime.check_workflow_budget() directly — each call IS a gate hit.
With budget=$5.00 and 3 calls, all should ALLOW.
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import time
from nullrun import init_or_die, shutdown
from nullrun import get_runtime
from nullrun.breaker.exceptions import WorkflowKilledInterrupt

init_or_die()
runtime = get_runtime()

TOTAL = 3
allow = 0
block = 0
first_block = None
start = time.monotonic()

try:
    for i in range(TOTAL):
        try:
            runtime.check_workflow_budget()
            allow += 1
            print(f"[{i}] t={time.monotonic()-start:.3f}s allow")
        except WorkflowKilledInterrupt as exc:
            block += 1
            if first_block is None:
                first_block = i
            print(f"[{i}] t={time.monotonic()-start:.3f}s BLOCK code={getattr(exc,'code',None)} msg={str(exc)[:120]!r}")
        except Exception as e:
            block += 1
            print(f"[{i}] t={time.monotonic()-start:.3f}s OTHER-EXC type={type(e).__name__} msg={str(e)[:120]!r}")
finally:
    shutdown()

print(f"=== SUMMARY ===")
print(f"  total={TOTAL} allow={allow} block={block}")
print(f"  VERDICT: {'PASS' if allow == TOTAL else 'FAIL' if block == TOTAL else f'MIXED (allow={allow},block={block})'}")