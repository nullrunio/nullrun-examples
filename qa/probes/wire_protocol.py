"""
TC-SDKG-001..004: Wire protocol header — missing, too old, too new, malformed.

Endpoint migration (2026-09-10): POST /api/v1/check → POST /api/v1/gate.
The /check endpoint was removed in the v3 consolidation (2026-06-27)
and replaced by /gate; pre-migration the probe was hitting a
nonexistent URL and getting 404s instead of the protocol-header
400s the test is designed to assert. The migration keeps the wire
shape identical (X-NULLRUN-PROTOCOL header + same JSON body) so
the TC-SDKG-001..004 contract is preserved.
"""
from __future__ import annotations
import os
import json
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")
ORG_ID = os.environ.get("NULLRUN_ORG_ID", "")
WORKFLOW_ID = os.environ.get("NULLRUN_WORKFLOW_ID", "")


def main():
    out = {}
    base_body = {
        "workflow_id": WORKFLOW_ID,
        "tools": ["echo"],
        "estimated_tokens": 10,
        "model": "gpt-4o-mini",
    }

    cases = [
        ("TC-SDKG-001", "missing", None, 400),
        ("TC-SDKG-002", "too_old", "1", 400),
        ("TC-SDKG-003", "too_new", "99", 400),
        ("TC-SDKG-004", "malformed", "not_a_number", 400),
    ]

    for tc_id, label, proto_val, expected in cases:
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        if proto_val is not None:
            headers["X-NULLRUN-PROTOCOL"] = proto_val
        r = httpx.post(f"{API_URL}/api/v1/gate",
                       headers=headers, json=base_body, timeout=10)
        out[tc_id] = {
            "label": label,
            "protocol_header": proto_val,
            "status": r.status_code,
            "expected": expected,
            "ok": r.status_code == expected,
        }
        try:
            j = r.json()
            out[tc_id]["error_code"] = j.get("error", {}).get("code") or j.get("code")
        except Exception:
            pass

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
