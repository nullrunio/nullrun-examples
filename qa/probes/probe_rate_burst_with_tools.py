"""Rate limit probe with tools populated.

TC-SDK-012 verification — corrected to send `tools` field so the
orchestrator's TB-1 fail-CLOSED branch doesn't shadow Step 2 rate_limit.
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import os, time
from nullrun import init_or_die, shutdown, set_call_context
from nullrun import get_runtime
from nullrun.breaker.exceptions import WorkflowKilledInterrupt

init_or_die()
runtime = get_runtime()

# Set tools to a non-blocked tool so TB-1 doesn't fire
set_call_context(tools=['read_file'])

TOTAL = 8  # cap=5, so 6th-8th should block
allow = 0
block = 0
first_block = None
first_block_t = None
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
                first_block_t = time.monotonic() - start
            print(f"[{i}] t={time.monotonic()-start:.3f}s BLOCK code={getattr(exc,'code',None)} msg={str(exc)[:120]!r}")
        except Exception as e:
            block += 1
            print(f"[{i}] t={time.monotonic()-start:.3f}s OTHER-EXC type={type(e).__name__} msg={str(e)[:120]!r}")
finally:
    shutdown()

print(f"=== SUMMARY ===")
print(f"  total={TOTAL} allow={allow} block={block}")
print(f"  first_block_i={first_block} first_block_t={first_block_t}")
print(f"  VERDICT: {'PASS' if first_block == 5 else 'UNEXPECTED (expected first_block=5)' if first_block is not None else 'FAIL (no block at all)'}")