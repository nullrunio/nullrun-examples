"""
TC-SDKT-007..008: CSRF bypass for Bearer (by-design), CSRF enforced without Bearer.
"""
from __future__ import annotations
import os
import sys
import json
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
EMAIL = "redacted-staging-user@example.test"
PASSWORD = "REDACTED_STAGING_PASSWORD"

def main():
    s = httpx.Client(base_url=API_URL, timeout=15)

    # Login first to get session cookie + CSRF token
    r = s.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        print(json.dumps({"error": "login_failed", "status": r.status_code}))
        sys.exit(2)

    csrf_token = None
    for c in s.cookies.jar:
        if c.name == "__Host-nullrun_csrf":
            csrf_token = c.value

    out = {}

    # TC-SDKT-007: CSRF bypass for Bearer (DELETE with Bearer present → 200)
    api_key = os.environ.get("NULLRUN_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}"}
    r7 = s.post("/api/v1/auth/session?_method=DELETE", headers=headers, timeout=10)
    out["TC-SDKT-007"] = {
        "status": r7.status_code,
        "expect": 200,
        "note": "logout attempt — 200 if OK, 401 if Bearer used for wrong endpoint, 403 if CSRF enforced"
    }

    # TC-SDKT-008: Logout without Bearer, no CSRF → 403
    no_csrf_headers = {"Cookie": ""}
    s2 = httpx.Client(base_url=API_URL, timeout=15)
    s2.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r8 = s2.post("/api/v1/auth/session?_method=DELETE", timeout=10)
    out["TC-SDKT-008"] = {
        "status": r8.status_code,
        "expect": 403,
        "note": "DELETE without CSRF token and without Bearer → 403"
    }

    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
