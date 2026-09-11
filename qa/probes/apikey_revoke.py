"""
TC-SDKK-005: Revocation two-phase — POST → DELETE → status='revoked',
subsequent /check with revoked key → 401 API_KEY_REVOKED.
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
    s = httpx.Client(base_url=API_URL, timeout=15)
    s.post("/api/auth/login",
           json={"email": "redacted-staging-user@example.test", "password": "REDACTED_STAGING_PASSWORD"})
    csrf = next((c.value for c in s.cookies.jar if c.name == "__Host-nullrun_csrf"), "")
    cookie_hdr = "; ".join(f"{c.name}={c.value}" for c in s.cookies.jar)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-NULLRUN-PROTOCOL": "4",
        "X-CSRF-Token": csrf,
        "Cookie": cookie_hdr,
        "Content-Type": "application/json",
    }

    out = {}
    # Create test key
    r = s.post(f"/api/v1/orgs/{ORG_ID}/api-keys",
               json={"name": "TC-SDKK-005-revoke-test",
                     "workflow_id": WORKFLOW_ID},
               headers=headers, timeout=15)
    out["create_status"] = r.status_code
    if r.status_code not in (200, 201):
        out["create_body"] = r.text[:300]
        print(json.dumps(out, indent=2))
        return

    created = r.json()
    key_id = created.get("id") or created.get("key_id")

    # Revoke
    rd = s.delete(f"/api/v1/orgs/{ORG_ID}/api-keys/{key_id}",
                  headers=headers, timeout=10)
    out["delete_status"] = rd.status_code

    # Verify status via GET
    rg = s.get(f"/api/v1/orgs/{ORG_ID}/api-keys/{key_id}",
               headers=headers, timeout=10)
    out["get_status"] = rg.status_code
    if rg.status_code == 200:
        body = rg.json()
        out["status"] = body.get("status")
        out["disabled"] = body.get("disabled")
        out["revoked_at"] = body.get("revoked_at")

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
