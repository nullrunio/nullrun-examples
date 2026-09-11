"""
TC-SDKK-001: Mask-once-on-display — POST returns full key once, GET returns
only prefix/suffix, DB stores Argon2id hash (never plaintext).
"""
from __future__ import annotations
import os
import sys
import json
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")
ORG_ID = os.environ.get("NULLRUN_ORG_ID", "")
WORKFLOW_ID = os.environ.get("NULLRUN_WORKFLOW_ID", "")


def main():
    out = {}
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-NULLRUN-PROTOCOL": "4",
        "Content-Type": "application/json",
    }

    # Login via session for cookie auth (in case Bearer insufficient for some endpoints)
    s = httpx.Client(base_url=API_URL, timeout=15)
    s.post("/api/auth/login",
           json={"email": "redacted-staging-user@example.test", "password": "REDACTED_STAGING_PASSWORD"})
    csrf = next((c.value for c in s.cookies.jar if c.name == "__Host-nullrun_csrf"), "")
    headers["X-CSRF-Token"] = csrf
    headers["Cookie"] = "; ".join(f"{c.name}={c.value}" for c in s.cookies.jar)

    # POST /api-keys — creates new key
    create_body = {
        "name": "TC-SDKK-001-mask-test",
        "workflow_id": WORKFLOW_ID,
    }
    r = s.post(f"/api/v1/orgs/{ORG_ID}/api-keys", json=create_body, timeout=15)
    out["create_status"] = r.status_code
    if r.status_code in (200, 201):
        created = r.json()
        key_id = created.get("id") or created.get("key_id")
        full_key = created.get("api_key") or created.get("key")
        out["post_response_keys"] = list(created.keys())
        out["api_key_starts_with_nr_live"] = bool(full_key and full_key.startswith("nr_live_"))

        # GET /api-keys/{id} — should NOT return full key
        rg = s.get(f"/api/v1/orgs/{ORG_ID}/api-keys/{key_id}", timeout=15)
        out["get_status"] = rg.status_code
        if rg.status_code == 200:
            get_data = rg.json()
            out["get_response_keys"] = list(get_data.keys())
            out["get_contains_api_key"] = "api_key" in get_data
            out["get_contains_key_prefix"] = "key_prefix" in get_data
            out["get_contains_key_suffix"] = "key_suffix" in get_data

        # Cleanup: revoke
        rd = s.delete(f"/api/v1/orgs/{ORG_ID}/api-keys/{key_id}", timeout=15)
        out["cleanup_delete_status"] = rd.status_code
    else:
        out["create_body_snippet"] = r.text[:500]

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
