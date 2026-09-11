"""UI bootstrap via BFF (next.js /api/orgs/* routes) — login, cleanup,
create fresh workflow + policy + api-key, write to .env.

Selector/auth notes:
- BFF login endpoint: POST /api/auth/login → sets __Host-nullrun_auth cookie
  (signed; contains organization_id).
- Admin CRUD via BFF: /api/orgs/{kind} (kind in workflows | policies |
  api-keys | approval-rules).
- The backend API (/api/v1/orgs/...) requires session-cookie admin auth
  via the BFF, not direct API-key Bearer.
"""
from __future__ import annotations

import os
import re
import sys
import json
import urllib.parse
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent
QA_DIR = EXAMPLES_DIR.parent / "qa"
ENV_PATH = EXAMPLES_DIR / ".env"
ENV_BACKUP = EXAMPLES_DIR / ".env.backup"
EMAIL = "redacted-staging-user@example.test"
PASSWORD = "REDACTED_STAGING_PASSWORD"
BFF_BASE = "https://nullrun.io"
LOG_DIR = QA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _login() -> tuple[str, str]:
    """Returns (auth_cookie_value, organization_id)."""
    import httpx
    with httpx.Client(base_url=BFF_BASE, timeout=20, follow_redirects=False) as c:
        r = c.post(
            "/api/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        if r.status_code not in (200, 302):
            raise RuntimeError(f"login failed: {r.status_code} {r.text[:200]}")
        auth_cookie = next(
            (ck.value for ck in c.cookies.jar if ck.name == "__Host-nullrun_auth"),
            "",
        )
        if not auth_cookie:
            raise RuntimeError("no __Host-nullrun_auth cookie in login response")
        decoded = urllib.parse.unquote(auth_cookie)
        m = re.match(r"(\{[^\{\}]*\})", decoded)
        if not m:
            raise RuntimeError(f"can't parse auth cookie: {decoded[:100]}")
        auth_data = json.loads(m.group(1))
        return auth_cookie, auth_data["organization_id"]


def _api(auth_cookie: str) -> "httpx.Client":
    import httpx
    c = httpx.Client(base_url=BFF_BASE, timeout=20)
    # Set the auth cookie exactly as the server returned it (URL-encoded)
    c.cookies.set("__Host-nullrun_auth", auth_cookie, domain="nullrun.io", path="/")
    return c


def _list(api, kind: str) -> list[dict]:
    r = api.get(f"/api/orgs/{kind}", timeout=15)
    if r.status_code != 200:
        return []
    data = r.json()
    if isinstance(data, dict):
        # Try common shapes: {kind: [...]} or {items: [...]} or {results: [...]}
        items = data.get(kind) or data.get("items") or data.get("results") or []
        if not items and kind.endswith("s"):
            # policies / api-keys / workflows / approval-rules (singular key)
            items = data.get(kind[:-1] + "_list") or data.get(kind[:-1]) or []
        return items
    if isinstance(data, list):
        return data
    return []


def _delete(api, kind: str, eid: str) -> int:
    r = api.delete(f"/api/orgs/{kind}/{eid}", timeout=15)
    return r.status_code


def _create_workflow(api, name: str) -> str:
    r = api.post("/api/orgs/workflows", json={"name": name}, timeout=15)
    print(f"      POST /workflows → {r.status_code}")
    if r.status_code not in (200, 201):
        print(f"      body: {r.text[:200]}")
        raise RuntimeError(f"workflow create failed: {r.status_code}")
    data = r.json()
    wf = data.get("workflow") if isinstance(data, dict) and "workflow" in data else data
    if isinstance(wf, list):
        wf = wf[0] if wf else {}
    return wf.get("id") or wf.get("workflow_id")


def _create_policy(api, workflow_id: str, name: str) -> str:
    # Wire enum is RateLimit | BudgetLimit | ToolBlock (per 422 response).
    # BFF policy create — BudgetLimit + Soft enforcement, 500c budget.
    r = api.post(
        "/api/orgs/policies",
        json={
            "name": name,
            "policy_type": "BudgetLimit",
            "scope": "workflow",
            "scope_id": workflow_id,
            "enforcement_mode": "Soft",
            "config": {
                "budget_cents": 500,
                "max_cents": 500,
            },
        },
        timeout=15,
    )
    print(f"      POST /policies → {r.status_code}")
    if r.status_code not in (200, 201):
        print(f"      body: {r.text[:300]}")
        raise RuntimeError(f"policy create failed: {r.status_code}")
    data = r.json()
    pol = data.get("policy") if isinstance(data, dict) and "policy" in data else data
    return pol.get("id") or pol.get("policy_id")


def _create_api_key(api, workflow_id: str, name: str) -> str:
    r = api.post(
        "/api/orgs/api-keys",
        json={
            "name": name,
            "workflow_id": workflow_id,
        },
        timeout=15,
    )
    print(f"      POST /api-keys → {r.status_code}")
    if r.status_code not in (200, 201):
        print(f"      body: {r.text[:300]}")
        raise RuntimeError(f"api-key create failed: {r.status_code}")
    data = r.json()
    ak = data.get("api_key") if isinstance(data, dict) and "api_key" in data else data
    if isinstance(ak, dict):
        return (
            ak.get("key")
            or ak.get("plain_key")
            or ak.get("api_key")
            or ak.get("full_key")
            or ""
        )
    if isinstance(ak, str):
        return ak
    return ""


def _write_env(api_key: str, workflow_id: str, org_id: str) -> "Path":
    # First, make sure ENV_PATH exists; restore from backup if needed
    if not ENV_PATH.exists():
        if ENV_BACKUP.exists():
            ENV_PATH.write_text(
                ENV_BACKUP.read_text(encoding="utf-8"), encoding="utf-8"
            )
        elif (EXAMPLES_DIR / ".env.example").exists():
            ENV_PATH.write_text(
                (EXAMPLES_DIR / ".env.example").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            ENV_PATH.write_text("", encoding="utf-8")

    # Read existing content BEFORE renaming
    original = ENV_PATH.read_text(encoding="utf-8")

    # Choose backup target
    backup_target = ENV_BACKUP
    import time
    while backup_target.exists():
        backup_target = ENV_PATH.with_suffix(
            f".env.backup.{int(time.time() * 1000)}"
        )
    ENV_PATH.rename(backup_target)

    new_lines = []
    replaced = {"api_key": False, "wf": False, "org": False}
    for line in original.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if stripped.startswith("NULLRUN_API_KEY="):
            new_lines.append(f"NULLRUN_API_KEY={api_key}")
            replaced["api_key"] = True
        elif stripped.startswith("NULLRUN_WORKFLOW_ID="):
            new_lines.append(f"NULLRUN_WORKFLOW_ID={workflow_id}")
            replaced["wf"] = True
        elif stripped.startswith("NULLRUN_ORG_ID="):
            new_lines.append(f"NULLRUN_ORG_ID={org_id}")
            replaced["org"] = True
        else:
            new_lines.append(line)
    if not replaced["api_key"]:
        new_lines.append(f"NULLRUN_API_KEY={api_key}")
    if not replaced["wf"]:
        new_lines.append(f"NULLRUN_WORKFLOW_ID={workflow_id}")
    if not replaced["org"]:
        new_lines.append(f"NULLRUN_ORG_ID={org_id}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return backup_target


def main() -> int:
    print("[1/6] Login via BFF")
    auth_cookie, org_id = _login()
    print(f"      org_id: {org_id}")
    api = _api(auth_cookie)

    print("[2/6] Cleanup (FK-safe: api-keys → policies → approval-rules → workflows)")
    for kind in ("api-keys", "policies", "approval-rules", "workflows"):
        try:
            items = _list(api, kind)
        except Exception as e:
            print(f"      list {kind}: error {e}")
            continue
        print(f"      {kind}: {len(items)} found")
        for item in items:
            eid = (
                item.get("id")
                or item.get("workflow_id")
                or item.get("policy_id")
                or item.get("key_id")
                or item.get("rule_id")
            )
            if not eid:
                continue
            status = _delete(api, kind, eid)
            name = (item.get("name") or "")[:30]
            print(f"        delete {kind}/{eid[:8]} {name!r} → {status}")

    print("[3/6] Create fresh workflow")
    wf_name = "E2E-test-wf-20260910"
    workflow_id = _create_workflow(api, wf_name)
    print(f"      workflow_id: {workflow_id}")

    print("[4/6] Create fresh policy (Soft budget 50000c + Hard tool-block)")
    pol_name = "E2E-test-pol-20260910"
    policy_id = _create_policy(api, workflow_id, pol_name)
    print(f"      policy_id: {policy_id}")
    # Bump budget immediately so probes don't trip period counter
    r = api.patch(
        f"/api/orgs/policies/{policy_id}",
        json={"config": {"budget_cents": 50000, "max_cents": 50000}},
        timeout=15,
    )
    print(f"      PATCH budget bump: {r.status_code} budget={r.json().get('budget_cents')}")
    # Add a Hard tool-block policy too
    tb_name = "E2E-test-toolblock-20260910"
    r = api.post(
        "/api/orgs/policies",
        json={
            "name": tb_name,
            "policy_type": "ToolBlock",
            "scope": "workflow",
            "scope_id": workflow_id,
            "enforcement_mode": "Hard",
            "config": {"tool_pattern": ["bash", "bash.*"]},
        },
        timeout=15,
    )
    print(f"      POST tool-block: {r.status_code}")
    if r.status_code in (200, 201):
        tb_id = r.json().get("policy", {}).get("id")
        if tb_id:
            r = api.patch(
                f"/api/orgs/policies/{tb_id}",
                json={
                    "config": {
                        "tool_pattern": ["bash", "bash.*"],
                        "budget_cents": 50000,
                        "max_cents": 50000,
                    }
                },
                timeout=15,
            )
            print(f"      PATCH tool-block bump: {r.status_code} budget={r.json().get('budget_cents')}")

    print("[5/6] Create fresh api-key")
    key_name = "E2E-test-key-20260910"
    api_key = _create_api_key(api, workflow_id, key_name)
    print(f"      api_key: {api_key[:14] + '...' + api_key[-4:] if len(api_key) > 18 else api_key or 'NOT FOUND'}")

    print("[6/6] Write to .env")
    if api_key:
        backup_target = _write_env(api_key, workflow_id, org_id)
        print(f"      wrote to {ENV_PATH}")
        print(f"      backup at {backup_target}")
    else:
        print("      [!] api_key empty — .env untouched")

    return 0


if __name__ == "__main__":
    sys.exit(main())
