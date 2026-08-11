"""SDK init smoke test — verifies the key + URL parse and the runtime is reachable.

Run:
    pip install nullrun
    export NULLRUN_API_KEY=nr_live_...
    python examples/smoke_test.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

import nullrun
from nullrun import init, init_or_die, shutdown, status

api_key = os.environ.get("NULLRUN_API_KEY", "")
api_url = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
print(f"Using key: {api_key[:12]}...{api_key[-4:]} ({len(api_key)} chars)")

try:
    init_or_die(api_key=api_key, api_url=api_url)
    print("SDK init: OK")
    s = status()
    print(f"Status: {s}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
finally:
    # Clean WebSocket close so the backend does not log
    # "Connection reset without closing handshake". No-op if init() never ran.
    shutdown()
