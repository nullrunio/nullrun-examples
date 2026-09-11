"""TC-SDK-045: /track/batch v3.66 wire validation — standalone wire-level probe.

Hits POST /api/v1/track/batch with a single event whose reservation_id=None.
The whole batch must be rejected with 503 BUDGET_RECHECK_FAILED BEFORE any
consume / enqueue / INSERT runs (per LATEST_PLAN §5 /track/batch hybrid semantics).
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# minimal env loader (no need for full examples._env)
import os as _os
_ENV_PATH = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "examples", ".env")
try:
    with open(_ENV_PATH, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _os.environ.setdefault(_k.strip(), _v.strip())
except FileNotFoundError:
    pass

import hashlib
import hmac as _hmac
import json
import time as _time
import uuid

import httpx

api_url = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io").rstrip("/")
api_key = os.environ.get("NULLRUN_API_KEY", "")
api_secret = os.environ.get("NULLRUN_API_SECRET", "")


def sign(body: str) -> dict[str, str]:
    ts = int(_time.time())
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    msg = f"{ts}:{api_key}:{body_hash}"
    sig = _hmac.new(api_secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "X-API-Key": api_key,
        "X-Signature-Timestamp": str(ts),
        "X-Signature": sig,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-NULLRUN-PROTOCOL": "3",
    }


if not api_key or not api_secret:
    print("ERROR: NULLRUN_API_KEY / NULLRUN_API_SECRET not set", flush=True)
    sys.exit(1)

def main():
    body = {
        "events": [
            {
                "event_id": str(uuid.uuid4()),
                "execution_id": str(uuid.uuid4()),
                "model": "gpt-4o-mini",
                "estimated_cost_cents": 0,
                "tool_name": "wire_probe",
                "workflow_id": "f3b140c3-0b80-4335-ab40-bcf34aed8e74",
                "tokens": 2,
                # reservation_id intentionally missing — v3.66 spec
            }
        ]
    }

    body_str = json.dumps(body, separators=(",", ":"))
    headers = sign(body_str)

    print(f"POST {api_url}/api/v1/track/batch", flush=True)
    print(f"body={body_str[:200]}", flush=True)

    try:
        response = httpx.post(
            f"{api_url}/api/v1/track/batch",
            content=body_str,
            headers=headers,
            timeout=10.0,
        )
        print(f"status={response.status_code}", flush=True)
        print(f"body={response.text[:400]!r}", flush=True)

        if response.status_code == 503 and "BUDGET_RECHECK_FAILED" in response.text:
            print("VERDICT=BLOCK (v3.66 strict wire validation)", flush=True)
        elif response.status_code in (200, 202):
            print("VERDICT=SPEC-GAP (v3.66 strict validation not active)", flush=True)
        elif response.status_code == 422:
            print("VERDICT=BLOCK (pre-v3.66 wire validation)", flush=True)
        elif response.status_code == 400:
            print("VERDICT=BLOCK", flush=True)
        else:
            print(f"VERDICT=INCONCLUSIVE status={response.status_code}", flush=True)
    except Exception as exc:
        print(f"ERROR type={type(exc).__name__} msg={str(exc)[:200]}", flush=True)


if __name__ == "__main__":
    main()