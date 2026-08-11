"""RATE-01..04 probe: 8 sequential no-LLM gate calls, expect 5 ALLOW + 3 BLOCK.
Uses runtime.check_workflow_budget() with chain context (for RATE-04 call-count match).
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import os, time, json, pathlib

from nullrun import init_or_die, shutdown, get_runtime
from nullrun.breaker.exceptions import WorkflowKilledInterrupt

# Override the API key from a sidecar file if present. Lets a CI driver
# pin a specific workflow's key without leaking it into the main .env.
# Falls back to whatever load_env() set above.
key_override = pathlib.Path(__file__).parent / ".probe_key"
if key_override.exists():
    os.environ["NULLRUN_API_KEY"] = key_override.read_text(encoding="utf-8").strip()

LOG = pathlib.Path(os.environ.get(
    "LOG_PATH",
    str(pathlib.Path(__file__).resolve().parents[1] / "logs" / "S07-RATE-probe.log"),
))
LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text("", encoding="utf-8")
def log(m): LOG.write_text(LOG.read_text(encoding="utf-8") + m + "\n", encoding="utf-8")

log(f"[boot] NULLRUN_API_KEY prefix={os.environ['NULLRUN_API_KEY'][:18]}...")

init_or_die()
runtime = get_runtime()
log("[boot] init_or_die OK")

TOTAL = 8  # cap=5/min, so 6-8 should block
allow = 0
block = 0
first_block = None
first_block_t = None
blocks_log = []
start = time.monotonic()

try:
    for i in range(TOTAL):
        try:
            runtime.check_workflow_budget()
            allow += 1
            log(f"[{i}] t={time.monotonic()-start:.3f}s allow")
        except WorkflowKilledInterrupt as exc:
            block += 1
            if first_block is None:
                first_block = i
                first_block_t = time.monotonic() - start
            log(f"[{i}] t={time.monotonic()-start:.3f}s BLOCK code={getattr(exc,'code',None)} msg={str(exc)[:200]!r}")
            blocks_log.append({"i": i, "code": getattr(exc, 'code', None), "msg": str(exc)[:200]})
        except Exception as e:
            block += 1
            log(f"[{i}] t={time.monotonic()-start:.3f}s OTHER-EXC type={type(e).__name__} msg={str(e)[:200]!r}")
finally:
    shutdown()

log(f"=== SUMMARY ===")
log(f"  total={TOTAL} allow={allow} block={block}")
log(f"  first_block_i={first_block} first_block_t={first_block_t}")
log(f"  blocks_log={json.dumps(blocks_log, default=str)}")
log(f"  VERDICT: {'PASS (RATE-01..03 expected: first_block=5)' if first_block == 5 else 'UNEXPECTED first_block=' + str(first_block) if first_block is not None else 'FAIL (no block)'}")