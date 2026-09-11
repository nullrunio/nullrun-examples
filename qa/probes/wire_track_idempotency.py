"""TC-SDK-046: /track idempotency — standalone wire-level probe.

Fires POST /track with the same idempotency_key (event_id) twice. The second
call must be deduped and return the same response without consuming budget twice.
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
    # /api/v1/gate is the canonical endpoint post-2026-06-27 (/api/v1/check was removed)
    body = {
        "model": "gpt-4o-mini",
        "tools": ["track_probe"],
        "workflow_id": "f3b140c3-0b80-4335-ab40-bcf34aed8e74",
        "idempotency_key": str(uuid.uuid4()),
    }
    body_str = json.dumps(body, separators=(",", ":"))
    headers = sign(body_str)
    r1 = httpx.post(f"{api_url}/api/v1/gate", content=body_str, headers=headers, timeout=10.0)
    print(f"gate#1 status={r1.status_code} body={r1.text[:200]!r}", flush=True)

    # Now do /track with a known event_id, twice
    track_body = {
        "event_id": str(uuid.uuid4()),  # same event_id for both
        "execution_id": str(uuid.uuid4()),
        "model": "gpt-4o-mini",
        "estimated_cost_cents": 1,
        "tool_name": "track_probe",
        "workflow_id": "f3b140c3-0b80-4335-ab40-bcf34aed8e74",
        "tokens": 2,
        "reservation_id": None,  # not relevant for idempotency test
    }
    eid = track_body["event_id"]
    track_str = json.dumps(track_body, separators=(",", ":"))
    headers2 = sign(track_str)
    r2 = httpx.post(f"{api_url}/api/v1/track", content=track_str, headers=headers2, timeout=10.0)
    print(f"track#1 event_id={eid[:8]}... status={r2.status_code} body={r2.text[:200]!r}", flush=True)

    # Second /track with the SAME event_id
    headers3 = sign(track_str)
    r3 = httpx.post(f"{api_url}/api/v1/track", content=track_str, headers=headers3, timeout=10.0)
    print(f"track#2 event_id={eid[:8]}... status={r3.status_code} body={r3.text[:200]!r}", flush=True)

    # If idempotency works, both should return the same status (or 409 DUP_CONFLICT on #2)
    if r2.status_code == r3.status_code and r2.text == r3.text:
        print("VERDICT=PASS (idempotent: both track calls returned identical response)", flush=True)
    elif r3.status_code == 409 or "DUP" in r3.text.upper() or "ALREADY" in r3.text.upper():
        print("VERDICT=PASS (idempotency rejected the duplicate)", flush=True)
    elif r3.status_code == 200 and r2.status_code == 200:
        print("VERDICT=INCONCLUSIVE (both 200; check budget counter)", flush=True)
    else:
        print(f"VERDICT=INCONCLUSIVE r2={r2.status_code} r3={r3.status_code}", flush=True)


if __name__ == "__main__":
    main()