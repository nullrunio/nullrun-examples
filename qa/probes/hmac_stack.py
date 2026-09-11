"""
TC-SDKT-001..006: HMAC wire gate (full stack, Bearer-only rejection, invalid key,
invalid signature, timestamp skew, CRLF normalization).

Per plan §4.1, all 6 TCs use httpx direct (wire-probe). Requires:
- NULLRUN_API_KEY (Bearer key, full nr_live_*)
- NULLRUN_API_SECRET (HMAC secret)
- NULLRUN_ORG_ID, NULLRUN_WORKFLOW_ID
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

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")
API_SECRET = os.environ.get("NULLRUN_API_SECRET", "")
ORG_ID = os.environ.get("NULLRUN_ORG_ID", "")
WORKFLOW_ID = os.environ.get("NULLRUN_WORKFLOW_ID", "")


def signed_headers(body: bytes, ts: int | None = None) -> dict:
    """Build X-API-Key + X-Signature + X-Signature-Timestamp headers."""
    if ts is None:
        ts = int(time.time())
    body_sha = hashlib.sha256(body).hexdigest()
    msg = f"{ts}:{API_KEY}:{body_sha}".encode()
    sig = hmac.new(API_SECRET.encode(), msg, hashlib.sha256).hexdigest()
    return {
        "X-API-Key": API_KEY,
        "X-Signature": sig,
        "X-Signature-Timestamp": str(ts),
        "X-NULLRUN-PROTOCOL": "3",
        "Content-Type": "application/json",
    }


def body() -> bytes:
    return json.dumps({
        "workflow_id": WORKFLOW_ID,
        "organization_id": ORG_ID,
        "execution_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "mode": "execute",
        "tools": ["echo"],
        "estimated_tokens": 10,
        "model": "gpt-4o-mini",
        "idempotency_key": f"hmac-{int(time.time()*1000)}",
    }).encode()


def run_tc(tc_id: str, label: str, headers: dict, body_b: bytes = None,
           expect_status: int = None, expect_code: str = None):
    body_b = body_b if body_b is not None else body()
    try:
        r = httpx.post(f"{API_URL}/api/v1/gate", headers=headers, content=body_b, timeout=15)
        ok = (r.status_code == expect_status) if expect_status else True
        out = {"tc": tc_id, "label": label, "status": r.status_code}
        try:
            j = r.json()
            out["error_code"] = j.get("error", {}).get("code") or j.get("code")
        except Exception:
            pass
        out["ok"] = ok
        print(json.dumps(out))
    except Exception as e:
        print(json.dumps({"tc": tc_id, "label": label, "exception": str(e)[:200]}))


def main():
    if not all([API_KEY, API_SECRET, ORG_ID, WORKFLOW_ID]):
        print(json.dumps({"error": "missing env: NULLRUN_API_KEY/SECRET/ORG_ID/WORKFLOW_ID"}))
        sys.exit(2)

    body_b = body()

    # TC-SDKT-001: Full HMAC stack required on /gate → 200
    run_tc("TC-SDKT-001", "full HMAC stack",
           {**signed_headers(body_b), "Authorization": f"Bearer {API_KEY}"},
           body_b, expect_status=200)

    # TC-SDKT-002: Bearer-only rejected (HMAC gate precedes Bearer) → 401 API_KEY_MISSING
    bearer_only = {
        "Authorization": f"Bearer {API_KEY}",
        "X-NULLRUN-PROTOCOL": "3",
        "Content-Type": "application/json",
    }
    run_tc("TC-SDKT-002", "bearer-only rejected", bearer_only,
           body_b, expect_status=401)

    # TC-SDKT-003: Invalid X-API-Key + valid HMAC → 401 API_KEY_INVALID
    bad_key_headers = signed_headers(body_b)
    bad_key_headers["X-API-Key"] = "nr_live_" + "0" * 36
    run_tc("TC-SDKT-003", "invalid X-API-Key", bad_key_headers,
           body_b, expect_status=401)

    # TC-SDKT-004: Invalid X-Signature (well-formed key, bad sig) → 401 HMAC_MISMATCH
    bad_sig_headers = signed_headers(body_b)
    bad_sig_headers["X-Signature"] = "0" * 64
    run_tc("TC-SDKT-004", "invalid X-Signature", bad_sig_headers,
           body_b, expect_status=401)

    # TC-SDKT-005: X-Signature-Timestamp skew >300s → 401 HMAC_TIMESTAMP_SKEW
    skew_headers = signed_headers(body_b, ts=int(time.time()) - 400)
    run_tc("TC-SDKT-005", "timestamp skew >300s", skew_headers,
           body_b, expect_status=401)

    # TC-SDKT-006: HMAC CRLF normalization (JSON field with \r\n)
    crlf_body = json.dumps({
        "workflow_id": WORKFLOW_ID,
        "organization_id": ORG_ID,
        "execution_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "mode": "execute",
        "tools": ["echo\r\nignore_me"],
        "estimated_tokens": 10,
        "model": "gpt-4o-mini",
        "idempotency_key": f"hmac-crlf-{int(time.time()*1000)}",
    }).encode()
    run_tc("TC-SDKT-006", "CRLF normalization", signed_headers(crlf_body),
           crlf_body, expect_status=422)


if __name__ == "__main__":
    main()
