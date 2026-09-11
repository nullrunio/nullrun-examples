"""
TS-12f /track/batch INVALID event probe — verify per-event rejection detail.
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
    print("=== TC-SDK-ERR-15: batch with mixed valid/invalid events ===")
    valid_event = {
        "workflow_id": WF_ID,
        "tokens": 100,
        "cost_cents": 1,
        "cost_source": "provisional",
        "reservation_id": str(uuid.uuid4()),
        "idempotency_key": str(uuid.uuid4()),
    }
    invalid_event = {
        "workflow_id": WF_ID,
        # missing reservation_id, missing idempotency_key, missing tokens
        "cost_cents": 1,
        "cost_source": "provisional",
    }
    body = {"events": [valid_event, invalid_event, valid_event]}
    body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = _sign(body_bytes)
    r = httpx.post(f"{API_URL}/api/v1/track/batch", content=body_bytes, headers=headers, timeout=10.0)
    print(f"status_code: {r.status_code}")
    print(f"body: {r.text[:800]}")
    print()
    print(f"=== TC-SDK-ERR-15 strict-wire validation: missing reservation_id ===")
    bad_event = {
        "workflow_id": WF_ID,
        "tokens": 100,
        "cost_cents": 1,
        "cost_source": "provisional",
        # reservation_id OMITTED entirely → strict wire violation §15 v3.66
        "idempotency_key": str(uuid.uuid4()),
    }
    body2 = {"events": [bad_event]}
    body_bytes2 = json.dumps(body2, separators=(",", ":")).encode("utf-8")
    headers2 = _sign(body_bytes2)
    r2 = httpx.post(f"{API_URL}/api/v1/track/batch", content=body_bytes2, headers=headers2, timeout=10.0)
    print(f"status_code: {r2.status_code}")
    print(f"body: {r2.text[:600]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
