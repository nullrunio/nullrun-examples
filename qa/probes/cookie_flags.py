"""
TC-SDKT-009..012: Session cookie flags, session fixation impossibility,
logout invalidates session, rate-limit on auth endpoints.
"""
from __future__ import annotations
import os
import json
import sys
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
EMAIL = "redacted-staging-user@example.test"
PASSWORD = "REDACTED_STAGING_PASSWORD"


def main():
    out = {}

    # TC-SDKT-010: Session fixation impossible — anonymous has no session cookie
    s_anon = httpx.Client(base_url=API_URL, timeout=10)
    r_anon = s_anon.get("/login")
    anon_cookies = [c.name for c in s_anon.cookies.jar]
    out["TC-SDKT-010"] = {
        "anonymous_cookies": anon_cookies,
        "expect": "__Host-nullrun_session NOT in anonymous cookies",
        "pass": "__Host-nullrun_session" not in anon_cookies
    }

    # TC-SDKT-009: Login → capture Set-Cookie flags
    s = httpx.Client(base_url=API_URL, timeout=15)
    r = s.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD},
               headers={"Content-Type": "application/json"})
    set_cookies = r.headers.get_list("set-cookie")
    out["TC-SDKT-009"] = {
        "set_cookie_count": len(set_cookies),
        "set_cookie_values": [sc[:120] + ("..." if len(sc) > 120 else "") for sc in set_cookies],
        "expect": "__Host-nullrun_session + __Host-nullrun_csrf; HttpOnly; Secure; SameSite=Lax; Max-Age=604800",
    }

    # TC-SDKT-011: Logout invalidates session
    csrf_token = None
    session_cookie = None
    for c in s.cookies.jar:
        if c.name == "__Host-nullrun_csrf":
            csrf_token = c.value
        if c.name == "__Host-nullrun_session":
            session_cookie = c.value
    api_key = os.environ.get("NULLRUN_API_KEY", "")
    bearer_headers = {"Authorization": f"Bearer {api_key}"}
    r11 = s.post("/api/v1/auth/session?_method=DELETE",
                 headers=bearer_headers, timeout=10)
    out["TC-SDKT-011"] = {
        "logout_status": r11.status_code,
        "expect": "200 OK + Set-Cookie Max-Age=0 for both session+CSRF"
    }

    # Post-logout GET /audit-log with stale session -> 401
    s2 = httpx.Client(base_url=API_URL, timeout=10)
    if session_cookie:
        s2.cookies.set("__Host-nullrun_session", session_cookie)
    r_after = s2.get("/api/v1/orgs/4a27bcb8-b50c-4309-92e0-324984c076fd/audit-log",
                     timeout=10)
    out["TC-SDKT-011"]["post_logout_status"] = r_after.status_code

    # TC-SDKT-012: Rate limit on auth — 7 rapid POST /login with wrong password
    s3 = httpx.Client(base_url=API_URL, timeout=10)
    rates = []
    for i in range(7):
        rr = s3.post("/api/auth/login",
                     json={"email": "wrong@example.com", "password": "wrong"},
                     timeout=10)
        rates.append({"attempt": i + 1, "status": rr.status_code,
                      "retry_after": rr.headers.get("retry-after")})
    out["TC-SDKT-012"] = {
        "results": rates,
        "expect": "1-5: 401 INVALID_CREDENTIALS; 6-7: 429 with retry-after"
    }

    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
