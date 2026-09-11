"""
TS-12f /track/batch wire probe (Sprint N+1).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import uuid

import httpx

# Load shared .env (examples/.env) — repo root is 4 dirs up: ts12f/ -> probes/ -> qa/ -> <root>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples._env import load_env  # type: ignore

load_env()

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ["NULLRUN_API_KEY"]
SECRET_KEY = os.environ.get("NULLRUN_API_SECRET", "")
ORG_ID = os.environ["NULLRUN_ORG_ID"]
WF_ID = os.environ["NULLRUN_WORKFLOW_ID"]


def _sign(body: bytes) -> dict[str, str]:
    ts = int(time.time())
    bh = hashlib.sha256(body).hexdigest()
    msg = f"{ts}:{API_KEY}:{bh}".encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return {
        "X-API-Key": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "X-Signature-Timestamp": str(ts),
        "X-Signature": sig,
        "Content-Type": "application/json",
        "X-NULLRUN-PROTOCOL": "3",
    }


def main() -> int:
    # /track/batch probe — TS-12a showed endpoint dead-in-prod (always 503 BUDGET_RECHECK_FAILED).
    # TS-12f needs to verify either it's still dead, OR partial-batch wire shape if active.
    events = [
        {"workflow_id": WF_ID, "tokens": 100, "cost_cents": 1, "cost_source": "provisional",
         "reservation_id": str(uuid.uuid4()), "idempotency_key": str(uuid.uuid4())},
        {"workflow_id": WF_ID, "tokens": 200, "cost_cents": 1, "cost_source": "provisional",
         "reservation_id": str(uuid.uuid4()), "idempotency_key": str(uuid.uuid4())},
    ]
    body = {"events": events}
    body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = _sign(body_bytes)
    r = httpx.post(f"{API_URL}/api/v1/track/batch", content=body_bytes, headers=headers, timeout=10.0)
    print(f"status_code: {r.status_code}")
    print(f"content_type: {r.headers.get('content-type')}")
    print(f"body: {r.text[:600]}")
    print()
    print(f"=== TC-SDK-ERR-15 observations ===")
    print(f"empty body: {len(r.text.strip()) == 0}")
    print(f"wire envelope present: {'error_code' in r.text.lower() or 'code' in r.text.lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
