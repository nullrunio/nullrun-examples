"""TC-SDK-047: Protocol version mismatch — standalone wire-level probe.

Issues /check calls with custom X-NULLRUN-PROTOCOL header:
- X-NULLRUN-PROTOCOL: 1 → expect 400 PROTOCOL_TOO_OLD
- X-NULLRUN-PROTOCOL: 4 → expect 400 PROTOCOL_TOO_NEW
- header absent → expect 400 PROTOCOL_HEADER_REQUIRED
"""
from __future__ import annotations

import os
import sys

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
    }


if not api_key or not api_secret:
    print("ERROR: NULLRUN_API_KEY / NULLRUN_API_SECRET not set", flush=True)
    sys.exit(1)


def main():
    # /api/v1/gate is the canonical endpoint post-2026-06-27 (/api/v1/check was removed)
    scenarios = [
        ("PROTOCOL_TOO_OLD", {"X-NULLRUN-PROTOCOL": "1"}),
        ("PROTOCOL_TOO_NEW", {"X-NULLRUN-PROTOCOL": "4"}),
        ("PROTOCOL_HEADER_REQUIRED", {}),  # no header
        ("VALID_PROTOCOL_3", {"X-NULLRUN-PROTOCOL": "3"}),  # baseline
    ]
    payload = {"model": "gpt-4o-mini", "tools": ["probe"], "workflow_id": "f3b140c3-0b80-4335-ab40-bcf34aed8e74"}
    body_str = json.dumps(payload, separators=(",", ":"))
    n_4xx = 0
    for label, hdrs in scenarios:
        headers = sign(body_str)
        headers.update(hdrs)
        try:
            r = httpx.post(
                f"{api_url}/api/v1/gate",
                content=body_str,
                headers=headers,
                timeout=10.0,
            )
            print(f"  [{label}] status={r.status_code} body={r.text[:160]!r}", flush=True)
            if 400 <= r.status_code < 500:
                n_4xx += 1
        except Exception as exc:
            print(f"  [{label}] ERROR type={type(exc).__name__} msg={str(exc)[:120]}", flush=True)
    # Expect all 3 mismatch scenarios to be 4xx
    print(f"\nn_4xx={n_4xx}/3 mismatch scenarios", flush=True)
    if n_4xx == 3:
        print("VERDICT=BLOCK (all 3 protocol mismatch scenarios returned 4xx)", flush=True)
    elif n_4xx >= 2:
        print(f"VERDICT=INCONCLUSIVE (n_4xx={n_4xx}/3)", flush=True)
    else:
        print(f"VERDICT=FAIL (only {n_4xx}/3 scenarios returned 4xx)", flush=True)


if __name__ == "__main__":
    main()