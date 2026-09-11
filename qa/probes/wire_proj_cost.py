"""
TC-SDKG-008: projected_cost_cents is response-only, server-computed.
Client-supplied projected_cost_cents must NOT be accepted.

Endpoint migration (2026-09-10): POST /api/v1/check → POST /api/v1/gate.
The /check endpoint was removed in the v3 consolidation (2026-06-27)
and replaced by /gate; the test contract (server-computed
projected_cost_cents, client-supplied value ignored) is unchanged.
"""
from __future__ import annotations
import os
import json
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")
WORKFLOW_ID = os.environ.get("NULLRUN_WORKFLOW_ID", "")


def main():
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-NULLRUN-PROTOCOL": "4",
        "Content-Type": "application/json",
    }
    body = {
        "workflow_id": WORKFLOW_ID,
        "tools": ["echo"],
        "estimated_tokens": 100,
        "model": "gpt-4o-mini",
        "projected_cost_cents": 99999,  # client-supplied, must be IGNORED
    }
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=headers, json=body, timeout=15)
    out = {"status": r.status_code}
    try:
        j = r.json()
        srv_cost = j.get("projected_cost_cents") or j.get("cost", {}).get("projected_cents")
        out["server_projected_cost_cents"] = srv_cost
        out["client_supplied_was_99999"] = (srv_cost != 99999) if srv_cost is not None else "no_field"
        out["decision"] = j.get("decision") or j.get("verdict")
    except Exception as e:
        out["exception"] = str(e)[:200]
        out["body_snippet"] = r.text[:300]
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
