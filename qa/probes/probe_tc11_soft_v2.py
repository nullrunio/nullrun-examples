"""TC-SDK-011 v2 probe with detailed HTTP logging."""
from __future__ import annotations
import sys, pathlib, json
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import os, time, uuid
import httpx
from nullrun import init_or_die, shutdown, get_runtime, chain

# Patch httpx to dump raw HTTP responses
_orig_send = httpx.Client.send
def patched_send(self, request, **kw):
    r = _orig_send(self, request, **kw)
    try:
        body = r.content.decode("utf-8", errors="replace") if r.content else "<empty>"
    except Exception:
        body = "<unparseable>"
    sys.stderr.write(f"\n[RAW-HTTP] {request.method} {request.url}\n")
    sys.stderr.write(f"[RAW-HTTP] request_body={request.content[:800]!r}\n")
    sys.stderr.write(f"[RAW-HTTP] response_status={r.status_code}\n")
    sys.stderr.write(f"[RAW-BODY] {body[:1500]}\n")
    sys.stderr.flush()
    return r
httpx.Client.send = patched_send

init_or_die()
runtime = get_runtime()

chain_id = str(uuid.uuid4())
print(f"chain_id={chain_id}")

try:
    with chain(chain_id, op="start"):
        try:
            result = runtime.check_workflow_budget()
            print(f"ALLOW: {result}")
        except Exception as e:
            print(f"EXC: type={type(e).__name__} code={getattr(e, 'code', None)} msg={str(e)[:300]!r}")
            print(f"  details={getattr(e, 'details', None)}")
finally:
    shutdown()