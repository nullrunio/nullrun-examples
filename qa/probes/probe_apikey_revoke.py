"""B.2f — Probe that captures the EXACT HTTP response (status + body + headers) when an SDK call hits a REVOKED key.
Patches httpx in the SDK to dump raw HTTP response."""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import os, pathlib, sys

# Force the API key from TEST_API_KEY env (passed by parent process)
forced_key = os.environ.get("TEST_API_KEY", "")
if forced_key:
    os.environ["NULLRUN_API_KEY"] = forced_key

from nullrun import init_or_die, get_runtime, transport as nr_transport
import httpx

# Patch httpx.Client.send to dump the response before parsing
_orig_send = httpx.Client.send
def patched_send(self, request, **kw):
    r = _orig_send(self, request, **kw)
    try:
        body = r.content.decode("utf-8", errors="replace") if r.content else "<empty>"
    except Exception:
        body = "<unparseable>"
    sys.stderr.write(f"[RAW-HTTP] {request.method} {request.url} -> status={r.status_code} headers={dict(r.headers)}\n")
    sys.stderr.write(f"[RAW-BODY] {body[:1500]}\n")
    sys.stderr.flush()
    return r
httpx.Client.send = patched_send

# Log path is overridable via PROBE_LOG_PATH; falls back to a path next
# to this file. Keeps the probe out of the user-specific /Documents tree.
log = pathlib.Path(os.environ.get("PROBE_LOG_PATH", str(pathlib.Path(__file__).parent / "probe_apikey_revoke.log")))
log.parent.mkdir(parents=True, exist_ok=True)
def logf(m):
    with log.open("a", encoding="utf-8") as f:
        f.write(m + "\n")

# Test ACTIVE key
logf(f"[BOOT] starting with key prefix={os.environ['NULLRUN_API_KEY'][:18] if os.environ['NULLRUN_API_KEY'] else '<EMPTY>'}")
init_or_die()
runtime = get_runtime()

from nullrun.context import set_call_context
set_call_context(tools=["bash"])

try:
    runtime.check_workflow_budget()
    logf("[ACTIVE] ALLOW")
except Exception as e:
    logf(f"[ACTIVE] EXC type={type(e).__name__} msg={str(e)[:500]!r}")
