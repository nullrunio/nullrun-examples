"""
Inline test for TC-SDKT-007..012 using DELETE method (the _method=DELETE workaround
in csrf_bypass.py is not supported by the backend router).
"""
from __future__ import annotations
import os, json, time
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
EMAIL = "redacted-staging-user@example.test"
PASSWORD = "REDACTED_STAGING_PASSWORD"
API_KEY = os.environ.get("NULLRUN_API_KEY", "")

LOGIN_URL = "/api/v1/auth/login"
LOGOUT_URL = "/api/v1/auth/session"


def main():
    out = {}

    # TC-SDKT-009: Login + capture Set-Cookie flags
    s = httpx.Client(base_url=API_URL, timeout=15)
    r = s.post(LOGIN_URL, json={"email": EMAIL, "password": PASSWORD},
               headers={"Content-Type": "application/json"})
    set_cookies = r.headers.get_list("set-cookie")
    out["TC-SDKT-009"] = {
        "login_status": r.status_code,
        "set_cookie_count": len(set_cookies),
        "set_cookie_values": [sc for sc in set_cookies],
        "expect": "__Host-nullrun_session + __Host-nullrun_csrf with HttpOnly/Secure/SameSite=Lax/Path=/Max-Age=604800"
    }

    # TC-SDKT-007: CSRF bypass for Bearer on DELETE /session → expect 200
    r7 = s.delete(LOGOUT_URL, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=10)
    out["TC-SDKT-007"] = {
        "status": r7.status_code,
        "expect": 200,
        "note": "Bearer bypasses CSRF check",
        "set_cookie_after_logout": [sc[:120] for sc in r7.headers.get_list("set-cookie")]
    }

    # TC-SDKT-008: Logout without CSRF and without Bearer
    s2 = httpx.Client(base_url=API_URL, timeout=15)
    r2 = s2.post(LOGIN_URL, json={"email": EMAIL, "password": PASSWORD},
                 headers={"Content-Type": "application/json"})
    if r2.status_code == 200:
        r8 = s2.delete(LOGOUT_URL, timeout=10)
        out["TC-SDKT-008"] = {
            "status": r8.status_code,
            "expect": 403,
            "note": "DELETE without CSRF token and without Bearer should be 403"
        }
    else:
        out["TC-SDKT-008"] = {"status": "skipped", "reason": f"re-login failed {r2.status_code}"}

    # TC-SDKT-010: Session fixation impossible
    s_anon = httpx.Client(base_url=API_URL, timeout=10)
    r_anon = s_anon.get("/login")
    anon_cookies = [c.name for c in s_anon.cookies.jar]
    out["TC-SDKT-010"] = {
        "anonymous_cookies": anon_cookies,
        "expect": "__Host-nullrun_session NOT in anonymous cookies",
        "pass": "__Host-nullrun_session" not in anon_cookies
    }

    # TC-SDKT-011: Logout invalidates session
    s3 = httpx.Client(base_url=API_URL, timeout=15)
    r3 = s3.post(LOGIN_URL, json={"email": EMAIL, "password": PASSWORD},
                 headers={"Content-Type": "application/json"})
    sess_cookie_value = None
    csrf_value = None
    for c in s3.cookies.jar:
        if c.name == "__Host-nullrun_session":
            sess_cookie_value = c.value
        if c.name == "__Host-nullrun_csrf":
            csrf_value = c.value
    r11 = s3.delete(LOGOUT_URL,
                    headers={"X-CSRF-Token": csrf_value, "Authorization": f"Bearer {API_KEY}"},
                    timeout=10)
    s4 = httpx.Client(base_url=API_URL, timeout=10)
    if sess_cookie_value:
        s4.cookies.set("__Host-nullrun_session", sess_cookie_value)
    r_after = s4.get("/api/v1/orgs/4a27bcb8-b50c-4309-92e0-324984c076fd/audit-log",
                     timeout=10)
    out["TC-SDKT-011"] = {
        "logout_status": r11.status_code,
        "set_cookie_after_logout": [sc[:120] for sc in r11.headers.get_list("set-cookie")],
        "post_logout_status": r_after.status_code,
        "expect": "logout 200 + post-logout 401"
    }

    # TC-SDKT-012: Rate limit on auth — 7 rapid POST /login with wrong password
    s5 = httpx.Client(base_url=API_URL, timeout=10)
    rates = []
    for i in range(7):
        rr = s5.post(LOGIN_URL,
                     json={"email": "wrong@example.com", "password": "wrong"},
                     timeout=10)
        rates.append({"attempt": i + 1, "status": rr.status_code,
                      "retry_after": rr.headers.get("retry-after"),
                      "body": rr.text[:100]})
        time.sleep(0.5)
    out["TC-SDKT-012"] = {
        "results": rates,
        "expect": "1-5: 401 INVALID_CREDENTIALS; 6-7: 429 with retry-after"
    }

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
