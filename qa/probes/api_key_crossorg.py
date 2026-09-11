"""
TC-SDKK-004: Cross-org IDOR — DELETE on api-key with SENTINEL UUID
(00000000-0000-0000-0000-000000000000) → 404 NOT_FOUND.
"""
from __future__ import annotations
import os
import json
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")
ORG_ID = os.environ.get("NULLRUN_ORG_ID", "")
SENTINEL = "00000000-0000-0000-0000-000000000000"


def main():
    s = httpx.Client(base_url=API_URL, timeout=15)
    s.post("/api/auth/login",
           json={"email": "redacted-staging-user@example.test", "password": "REDACTED_STAGING_PASSWORD"})
    csrf = next((c.value for c in s.cookies.jar if c.name == "__Host-nullrun_csrf"), "")
    cookie_hdr = "; ".join(f"{c.name}={c.value}" for c in s.cookies.jar)
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-CSRF-Token": csrf,
        "Cookie": cookie_hdr,
    }

    r = s.delete(f"/api/v1/orgs/{ORG_ID}/api-keys/{SENTINEL}",
                 headers=headers, timeout=10)
    out = {
        "status": r.status_code,
        "expect": 404,
        "ok": r.status_code == 404,
        "body_snippet": r.text[:200] if r.text else "",
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
