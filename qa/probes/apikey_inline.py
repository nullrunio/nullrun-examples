"""
Inline verification for TC-SDKK-001/004/005.
The /api/v1/orgs/:org/api-keys endpoint uses X-API-Key header (not Bearer).
"""
from __future__ import annotations
import os, json
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")
ORG_ID = "4a27bcb8-b50c-4309-92e0-324984c076fd"
WORKFLOW_ID = "82dc8b59-0d20-4a17-b39d-c51c540be8d3"
SENTINEL = "00000000-0000-0000-0000-000000000000"


def main():
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }
    s = httpx.Client(base_url=API_URL, timeout=15)
    out = {}

    # TC-SDKK-001: GET list returns masked keys
    r = s.get(f"/api/v1/orgs/{ORG_ID}/api-keys", headers=headers, timeout=15)
    out["TC-SDKK-001"] = {
        "get_status": r.status_code,
    }
    if r.status_code == 200:
        data = r.json()
        items = data.get("data") or data.get("items") or data.get("keys") or []
        out["TC-SDKK-001"]["items_count"] = len(items)
        if items:
            first = items[0]
            out["TC-SDKK-001"]["body_keys_sample"] = list(first.keys())
            out["TC-SDKK-001"]["plaintext_leaked"] = (
                "api_key" in first or
                any(v == API_KEY for v in first.values() if isinstance(v, str))
            )
            out["TC-SDKK-001"]["has_prefix"] = "key_prefix" in first
            out["TC-SDKK-001"]["has_suffix"] = "key_suffix" in first
            out["TC-SDKK-001"]["sample_first"] = first
    else:
        out["TC-SDKK-001"]["raw"] = r.text[:300]

    # TC-SDKK-004: Cross-org IDOR — DELETE on SENTINEL UUID
    r = s.delete(f"/api/v1/orgs/{ORG_ID}/api-keys/{SENTINEL}",
                 headers=headers, timeout=10)
    out["TC-SDKK-004"] = {
        "delete_sentinel_status": r.status_code,
        "expect": 404,
        "ok": r.status_code == 404,
        "body_snippet": r.text[:200] if r.text else "",
    }

    # TC-SDKK-005: Revocation — verify existing key statuses
    r = s.get(f"/api/v1/orgs/{ORG_ID}/api-keys", headers=headers, timeout=15)
    if r.status_code == 200:
        data = r.json()
        items = data.get("data") or data.get("items") or data.get("keys") or []
        statuses = [it.get("status") for it in items if "status" in it]
        out["TC-SDKK-005"] = {
            "get_list_status": r.status_code,
            "items_count": len(items),
            "statuses_observed": statuses,
            "note": "POST /api/v1/orgs/:org/api-keys is NOT exposed in OpenAPI; only UI allows creation. Cannot exercise full revoke two-phase via API."
        }
    else:
        out["TC-SDKK-005"] = {"get_list_status": r.status_code}

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
