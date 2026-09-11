"""
TS-12f server-minted execution_id probe with action_digest (Allow path).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from typing import Any

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


def _action_digest(business_impact: dict[str, Any]) -> str:
    payload = "nullrun/v1/business_impact:" + json.dumps(business_impact, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    client_exec_id = "11111111-1111-1111-1111-111111111111"
    business_impact = {
        "kind": "money",
        "direction": "outflow",
        "amount_minor": 5000,
        "currency": "USD",
        "extractor_id": "nullrun.money.path",
        "extractor_version": "1",
    }
    body = {
        "organization_id": ORG_ID,
        "execution_id": client_exec_id,  # Client-supplied — server must IGNORE on Allow path
        "trace_id": str(uuid.uuid4()),
        "tool": "applife_pay",
        "input": {},
        "mode": "auto",
        "check_type": "llm",
        "model": "gpt-4o-mini",
        "operation_id": str(uuid.uuid4()),
        "tools": ["applife_pay"],
        "business_impact": business_impact,
        "action_digest": _action_digest(business_impact),
    }
    body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = _sign(body_bytes)
    r = httpx.post(f"{API_URL}/api/v1/gate", content=body_bytes, headers=headers, timeout=10.0)
    print(f"status_code: {r.status_code}")
    print(f"body: {r.text}")
    if r.status_code == 200:
        data = r.json()
        reservation_id = data.get("reservation_id")
        if reservation_id:
            try:
                v = uuid.UUID(reservation_id)
                print(f"reservation_id: {reservation_id}, variant={v.version}")
            except Exception:
                print(f"reservation_id (not UUID): {reservation_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
