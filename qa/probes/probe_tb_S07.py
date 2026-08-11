"""TB-01..09 probe: parameterized tool-list + chain context.
Each scenario specifies expected outcomes for a tool list. Probe
hits /check via runtime.check_workflow_budget() and inspects the
response.
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
from nullrun.context import set_call_context

# Override the API key from a sidecar file if present. Lets a CI driver
# pin a specific workflow's key without leaking it into the main .env.
# Falls back to whatever load_env() set above.
key_override = pathlib.Path(__file__).parent / ".probe_key"
if key_override.exists():
    os.environ["NULLRUN_API_KEY"] = key_override.read_text(encoding="utf-8").strip()

LOG = pathlib.Path(os.environ.get(
    "LOG_PATH",
    str(pathlib.Path(__file__).resolve().parents[1] / "logs" / "S07-TB-probe.log"),
))
LOG.parent.mkdir(parents=True, exist_ok=True)
if not LOG.exists() or os.environ.get("TB_RESET_LOG") == "1":
    LOG.write_text("", encoding="utf-8")
def log(m):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(m + "\n")

log(f"[boot] NULLRUN_API_KEY prefix={os.environ['NULLRUN_API_KEY'][:18]}...")
init_or_die()
runtime = get_runtime()
log("[boot] init_or_die OK")

# Patch Transport.check to dump request/response for diagnostics
from nullrun import transport as nr_transport
_orig_check = nr_transport.Transport.check
def patched_check(self, request_body, *args, **kwargs):
    log(f"[req] {json.dumps(request_body, default=str)[:600]}")
    res = _orig_check(self, request_body, *args, **kwargs)
    log(f"[resp] {json.dumps(res, default=str)[:600] if isinstance(res, dict) else str(res)[:300]}")
    return res
nr_transport.Transport.check = patched_check

SCENARIO = os.environ.get("TB_SCENARIO", "TB-01")
TOOL_LIST = os.environ.get("TB_TOOLS", "bash")
tools = [t.strip() for t in TOOL_LIST.split(",") if t.strip()]
log(f"[scenario] {SCENARIO} tools={tools}")

set_call_context(tools=tools)

start = time.monotonic()
try:
    runtime.check_workflow_budget()
    log(f"[RESULT] t={time.monotonic()-start:.3f}s ALLOW")
except WorkflowKilledInterrupt as e:
    log(f"[RESULT] t={time.monotonic()-start:.3f}s BLOCK code={getattr(e,'code',None)} msg={str(e)[:500]!r}")
except Exception as e:
    log(f"[RESULT] t={time.monotonic()-start:.3f}s OTHER-EXC type={type(e).__name__} msg={str(e)[:500]!r}")
finally:
    shutdown()
