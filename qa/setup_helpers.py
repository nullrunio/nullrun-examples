"""setup_helpers.py — Entity CRUD helpers per SDK_TEST §2.5 (v4.2).

Aligned with SDK_TEST.md v4.2 (2026-09-04): UI primary (§2.4), API fallback (§2.5).
This module provides BOTH paths so the runner can pick based on availability:

    API path (preferred when UI unavailable):
        NullRunAPI(api_key, org_id)
        api.create_workflow(name)
        api.create_policy(workflow_id, spec)
        api.create_api_key(workflow_id, name)
        api.create_approval_rule(workflow_id, name, matcher)
        api.delete_* (FK-safe order)

    UI path (primary per §2.4):
        NullRunUI(frontend_url)
        ui.login(email, password)
        ui.create_workflow_via_ui(name)
        ui.create_policy_via_ui(workflow_id, spec)
        ui.create_api_key_via_ui(workflow_id, name)

High-level helpers (preferred for runners):
    setup_workflow_with_budget(name, budget_cents, *, org_id, api_key, ui=None)
    setup_api_key(name, workflow_id, *, org_id, ui=None)
    setup_policy(spec, *, org_id, workflow_id, ui=None)
    setup_approval_rule(name, matcher, *, workflow_id, ui=None)
    teardown_workflow(workflow_id, *, ui=None)
    teardown_policy(policy_id, *, ui=None)
    teardown_api_key(key_id, *, ui=None)
    teardown_approval_rule(rule_id, *, ui=None)

Each helper returns a dict:
    {"creation_mode": "ui"|"api"|"ui_required",
     "<resource>_id": uuid,
     "fixture": {...metadata for rollback...}}
"""
from __future__ import annotations

import os
import json
import time
import uuid
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_API_URL = "https://api.nullrun.io"
DEFAULT_FRONTEND_URL = "https://nullrun.io"


# --------------------------------------------------------------------------- #
# NullRunAPI — HTTP client using session cookie (from UI login)
# --------------------------------------------------------------------------- #

class NullRunAPI:
    """Thin wrapper over httpx for admin CRUD endpoints.

    Backend admin endpoints (/api/v1/orgs/{org}/workflows, /policies, /api-keys,
    /approval-rules) require session cookie auth (Bearer returns 401). The
    standard pattern is:

        ui = NullRunUI()
        ui.login(email, password)
        api = NullRunAPI(session_cookie=ui.session_cookie, csrf_token=ui.csrf_token, org_id=...)
        api.create_workflow(...)

    For SDK endpoints (/gate, /track, /auth/verify, /capabilities), use the
    Bearer-auth helper NullRunSDKBridge instead.
    """

    def __init__(
        self,
        *,
        org_id: str,
        session_cookie: str | None = None,
        csrf_token: str | None = None,
        api_url: str = DEFAULT_API_URL,
        bearer_token: str | None = None,
    ):
        self.org_id = org_id
        self.api_url = api_url.rstrip("/")
        self.session_cookie = session_cookie or ""
        self.csrf_token = csrf_token or ""
        self.bearer_token = bearer_token or ""

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.session_cookie:
            h["Cookie"] = self.session_cookie
        if self.csrf_token:
            h["X-CSRF-Token"] = self.csrf_token
        if self.bearer_token:
            h["Authorization"] = f"Bearer {self.bearer_token}"
        return h

    def _request(self, method: str, path: str, *, payload: dict | None = None, timeout: float = 10.0):
        import httpx
        url = f"{self.api_url}{path}"
        r = httpx.request(method, url, json=payload, headers=self._headers(), timeout=timeout)
        try:
            body = r.json()
        except Exception:
            body = r.text
        return r.status_code, body

    # ----- workflows -----
    def list_workflows(self, org_id: str | None = None) -> list[dict]:
        oid = org_id or self.org_id
        s, b = self._request("GET", f"/api/v1/orgs/{oid}/workflows")
        return b if isinstance(b, list) else (b.get("workflows") if isinstance(b, dict) else [])

    def get_workflow(self, workflow_id: str) -> dict | None:
        s, b = self._request("GET", f"/api/v1/orgs/{self.org_id}/workflows/{workflow_id}")
        return b if isinstance(b, dict) and s == 200 else None

    def create_workflow(self, name: str, *, description: str = "") -> dict:
        s, b = self._request("POST", f"/api/v1/orgs/{self.org_id}/workflows",
                             payload={"name": name, "description": description})
        return {"status": s, "body": b}

    def delete_workflow(self, workflow_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/api/v1/orgs/{self.org_id}/workflows/{workflow_id}")

    # ----- policies -----
    def list_policies(self, org_id: str | None = None, workflow_id: str | None = None) -> list[dict]:
        oid = org_id or self.org_id
        if workflow_id:
            s, b = self._request("GET", f"/api/v1/orgs/{oid}/workflows/{workflow_id}/policies")
        else:
            s, b = self._request("GET", f"/api/v1/orgs/{oid}/policies")
        return b if isinstance(b, list) else (b.get("policies") if isinstance(b, dict) else [])

    def get_policy(self, policy_id: str) -> dict | None:
        s, b = self._request("GET", f"/api/v1/orgs/{self.org_id}/policies/{policy_id}")
        return b if isinstance(b, dict) and s == 200 else None

    def create_policy(self, spec: dict) -> dict:
        """Create a policy. spec keys: name, kind/policy_type, scope, workflow_id, type-specific."""
        s, b = self._request("POST", f"/api/v1/orgs/{self.org_id}/policies", payload=spec)
        return {"status": s, "body": b}

    def delete_policy(self, policy_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/api/v1/orgs/{self.org_id}/policies/{policy_id}")

    # ----- api-keys -----
    def list_api_keys(self, org_id: str | None = None) -> list[dict]:
        oid = org_id or self.org_id
        s, b = self._request("GET", f"/api/v1/orgs/{oid}/api-keys")
        return b if isinstance(b, list) else (b.get("api_keys") if isinstance(b, dict) else [])

    def create_api_key(self, workflow_id: str, name: str, scopes: list[str] | None = None) -> dict:
        payload = {"name": name, "workflow_id": workflow_id}
        if scopes:
            payload["scopes"] = scopes
        s, b = self._request("POST", f"/api/v1/orgs/{self.org_id}/api-keys", payload=payload)
        return {"status": s, "body": b}

    def revoke_api_key(self, key_id: str) -> tuple[int, Any]:
        return self._request("POST", f"/api/v1/orgs/{self.org_id}/api-keys/{key_id}/revoke")

    # ----- approval-rules -----
    def list_approval_rules(self, org_id: str | None = None, workflow_id: str | None = None) -> list[dict]:
        oid = org_id or self.org_id
        if workflow_id:
            s, b = self._request("GET", f"/api/v1/orgs/{oid}/workflows/{workflow_id}/approval-rules")
        else:
            s, b = self._request("GET", f"/api/v1/orgs/{oid}/approval-rules")
        return b if isinstance(b, list) else (b.get("approval_rules") if isinstance(b, dict) else [])

    def create_approval_rule(self, workflow_id: str, name: str, matcher: dict) -> dict:
        payload = {"name": name, "workflow_id": workflow_id, "matcher": matcher}
        s, b = self._request("POST", f"/api/v1/orgs/{self.org_id}/approval-rules", payload=payload)
        return {"status": s, "body": b}

    def delete_approval_rule(self, rule_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/api/v1/orgs/{self.org_id}/approval-rules/{rule_id}")


# --------------------------------------------------------------------------- #
# NullRunUI — Playwright-based UI automation (PRIMARY path per §2.4)
# --------------------------------------------------------------------------- #

class NullRunUI:
    """Playwright wrapper for UI-primary entity CRUD per §2.4.

    Usage:
        ui = NullRunUI()
        ui.login("user@example.com", "password")
        # ui.session_cookie and ui.csrf_token now populated
        api = NullRunAPI(org_id=..., session_cookie=ui.session_cookie, csrf_token=ui.csrf_token)
        ...
        ui.close()

    Falls back gracefully if Playwright browser is not installed (raises with
    clear remediation hint).
    """

    def __init__(self, frontend_url: str = DEFAULT_FRONTEND_URL, headless: bool = True):
        self.frontend_url = frontend_url.rstrip("/")
        self.headless = headless
        self._browser = None
        self._context = None
        self._page = None
        self.session_cookie = ""
        self.csrf_token = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _ensure_browser(self):
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "playwright not installed; cannot use UI path. "
                "Install: pip install playwright && playwright install chromium"
            ) from e
        pw = sync_playwright().start()
        self._browser = pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()

    def login(self, email: str, password: str, timeout_ms: int = 30000) -> dict:
        """Login via /login form. Stores session_cookie and csrf_token on success."""
        self._ensure_browser()
        self._page.goto(f"{self.frontend_url}/login", wait_until="domcontentloaded", timeout=timeout_ms)
        # Type credentials via keyboard (per auth-form-autofill-killswitch memory)
        self._page.fill('input[name="email"]', email)
        self._page.fill('input[name="password"]', password)
        self._page.click('button[type="submit"]')
        self._page.wait_for_url(lambda url: "/login" not in url, timeout=timeout_ms)
        # Extract session cookie + CSRF token
        cookies = self._context.cookies()
        for c in cookies:
            if c.get("name") == "__Host-nullrun_session":
                self.session_cookie = f"__Host-nullrun_session={c['value']}"
            elif c.get("name") == "__Host-nullrun_csrf":
                self.csrf_token = c.get("value", "")
        return {
            "session_cookie": self.session_cookie,
            "csrf_token": self.csrf_token,
            "url": self._page.url,
        }

    def create_workflow_via_ui(self, name: str, timeout_ms: int = 30000) -> dict:
        """Create a workflow via /control-center/workflows → New workflow."""
        self._ensure_browser()
        self._page.goto(f"{self.frontend_url}/control-center/workflows",
                        wait_until="domcontentloaded", timeout=timeout_ms)
        self._page.click('[data-testid="new-workflow"]', timeout=timeout_ms)
        self._page.fill('input[name="name"]', name)
        self._page.click('button[type="submit"]', timeout=timeout_ms)
        self._page.wait_for_url(lambda url: "/workflows/" in url and "/workflows?" not in url,
                                timeout=timeout_ms)
        # Extract workflow ID from URL
        url = self._page.url
        wf_id = url.split("/workflows/")[-1].split("?")[0]
        return {"workflow_id": wf_id, "url": url}

    def create_policy_via_ui(self, workflow_id: str, spec: dict, timeout_ms: int = 30000) -> dict:
        self._ensure_browser()
        self._page.goto(f"{self.frontend_url}/control-center/workflows/{workflow_id}/policies",
                        wait_until="domcontentloaded", timeout=timeout_ms)
        self._page.click('[data-testid="new-policy"]', timeout=timeout_ms)
        self._page.fill('input[name="name"]', spec.get("name", ""))
        # Type-specific fields — fill what we know
        if "budget_cents" in spec:
            self._page.fill('input[name="budget_cents"]', str(spec["budget_cents"]))
        if "enforcement_mode" in spec:
            self._page.select_option('select[name="enforcement_mode"]', spec["enforcement_mode"])
        self._page.click('button[type="submit"]', timeout=timeout_ms)
        self._page.wait_for_timeout(500)
        return {"status": "ui-created", "workflow_id": workflow_id}

    def create_api_key_via_ui(self, workflow_id: str, name: str, timeout_ms: int = 30000) -> dict:
        self._ensure_browser()
        self._page.goto(f"{self.frontend_url}/control-center/api-keys",
                        wait_until="domcontentloaded", timeout=timeout_ms)
        self._page.click('[data-testid="new-api-key"]', timeout=timeout_ms)
        self._page.fill('input[name="name"]', name)
        self._page.select_option('select[name="workflow_id"]', workflow_id)
        self._page.click('button[type="submit"]', timeout=timeout_ms)
        # Copy plain key from modal
        self._page.wait_for_selector('[data-testid="plain-api-key"]', timeout=timeout_ms)
        plain_key = self._page.text_content('[data-testid="plain-api-key"]') or ""
        return {"api_key": plain_key.strip(), "workflow_id": workflow_id}

    def close(self):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Ledger — per-RUN_ID cleanup tracking
# --------------------------------------------------------------------------- #

@dataclass
class Ledger:
    """Tracks created entities per RUN_ID for safe cleanup (§6.12 FK-safe order)."""
    run_id: str
    entries: list[dict] = field(default_factory=list)

    def add(self, kind: str, entity_id: str, fixture: dict | None = None):
        self.entries.append({"kind": kind, "id": entity_id, "fixture": fixture or {}})
        return self

    def save(self, path: str | None = None):
        path = path or f"qa/logs/{self.run_id}/ledger.json"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(
            {"run_id": self.run_id, "entries": self.entries},
            indent=2,
        ))

    def cleanup_via_api(self, api: NullRunAPI):
        """FK-safe reverse-order cleanup: workflows → policies → rules → keys."""
        # Group by kind for explicit order
        by_kind: dict[str, list[dict]] = {}
        for e in self.entries:
            by_kind.setdefault(e["kind"], []).append(e)

        # Workflows last (cascade deletes policies/rules/keys)
        for kind in ("api_key", "approval_rule", "policy"):
            for e in by_kind.get(kind, []):
                try:
                    if kind == "api_key":
                        api.revoke_api_key(e["id"])
                    elif kind == "approval_rule":
                        api.delete_approval_rule(e["id"])
                    elif kind == "policy":
                        api.delete_policy(e["id"])
                except Exception as ex:
                    print(f"cleanup {kind} {e['id']} failed: {ex}")
        for e in by_kind.get("workflow", []):
            try:
                api.delete_workflow(e["id"])
            except Exception as ex:
                print(f"cleanup workflow {e['id']} failed: {ex}")


# --------------------------------------------------------------------------- #
# High-level helpers (preferred entry points)
# --------------------------------------------------------------------------- #

def setup_workflow_with_budget(
    name: str,
    budget_cents: int,
    *,
    org_id: str,
    api_key: str | None = None,
    session_cookie: str | None = None,
    csrf_token: str | None = None,
    ui: NullRunUI | None = None,
    ledger: Ledger | None = None,
    enforcement_mode: str = "Hard",
) -> dict:
    """Create a workflow + attach a BUDGET policy with max_cents.

    Tries API path first (if session_cookie provided), else UI path (if ui
    instance provided), else returns ui_required marker.

    Returns dict with creation_mode, workflow_id, policy_id, fixture.
    """
    result = {"creation_mode": None, "workflow_id": None, "policy_id": None}

    # Step 1: Create workflow
    if session_cookie or csrf_token:
        # API path
        api = NullRunAPI(
            org_id=org_id,
            session_cookie=session_cookie or "",
            csrf_token=csrf_token or "",
            bearer_token=api_key or "",
        )
        r = api.create_workflow(name=name)
        if r["status"] in (200, 201):
            wf_id = (r["body"].get("id") or r["body"].get("workflow_id")) if isinstance(r["body"], dict) else None
            if wf_id:
                result["workflow_id"] = wf_id
                result["creation_mode"] = "api"

    if result["workflow_id"] is None and ui is not None:
        # UI fallback
        try:
            r = ui.create_workflow_via_ui(name)
            result["workflow_id"] = r["workflow_id"]
            result["creation_mode"] = "ui"
        except Exception as ex:
            return {
                "creation_mode": "ui_required",
                "error": str(ex),
                "remediation": "Run ui.login() first, or pass session_cookie+csrf_token explicitly.",
            }

    if result["workflow_id"] is None:
        return {
            "creation_mode": "ui_required",
            "remediation": "Provide ui=NullRunUI() or session_cookie+csrf_token. "
                            "Cannot create workflow without either.",
        }

    # Step 2: Attach BUDGET policy
    policy_spec = {
        "name": f"{name}-budget",
        "kind": "BUDGET",
        "policy_type": "BUDGET",
        "scope": "WORKFLOW",
        "workflow_id": result["workflow_id"],
        "budget_cents": budget_cents,
        "max_cents": budget_cents,
        "enforcement_mode": enforcement_mode,
    }
    if session_cookie or csrf_token:
        r = api.create_policy(policy_spec)
        if r["status"] in (200, 201):
            policy_id = (r["body"].get("id") or r["body"].get("policy_id")) if isinstance(r["body"], dict) else None
            result["policy_id"] = policy_id

    if result["policy_id"] is None and ui is not None:
        try:
            ui.create_policy_via_ui(result["workflow_id"], policy_spec)
            result["policy_id"] = f"ui-created:{policy_spec['name']}"
        except Exception:
            pass

    if ledger is not None and result["workflow_id"]:
        ledger.add("workflow", result["workflow_id"], {"name": name, "budget_cents": budget_cents})
    if ledger is not None and result["policy_id"]:
        ledger.add("policy", result["policy_id"], policy_spec)

    result["fixture"] = {"name": name, "budget_cents": budget_cents}
    return result


def setup_api_key(
    name: str,
    workflow_id: str,
    *,
    org_id: str,
    session_cookie: str | None = None,
    csrf_token: str | None = None,
    ui: NullRunUI | None = None,
    ledger: Ledger | None = None,
    scopes: list[str] | None = None,
) -> dict:
    """Create an API key bound to a workflow. Returns plain_key + key_id."""
    if session_cookie or csrf_token:
        api = NullRunAPI(
            org_id=org_id,
            session_cookie=session_cookie or "",
            csrf_token=csrf_token or "",
        )
        r = api.create_api_key(workflow_id, name, scopes=scopes)
        if r["status"] in (200, 201):
            body = r["body"] if isinstance(r["body"], dict) else {}
            plain = body.get("plain_key") or body.get("api_key") or body.get("key")
            kid = body.get("id") or body.get("key_id")
            if ledger and kid:
                ledger.add("api_key", kid, {"name": name, "workflow_id": workflow_id})
            return {
                "creation_mode": "api",
                "key_id": kid,
                "plain_key": plain,
                "fixture": {"name": name, "workflow_id": workflow_id},
            }

    if ui is not None:
        try:
            r = ui.create_api_key_via_ui(workflow_id, name)
            if ledger:
                ledger.add("api_key", "ui-created", {"name": name, "workflow_id": workflow_id})
            return {
                "creation_mode": "ui",
                "key_id": "ui-created",
                "plain_key": r["api_key"],
                "fixture": {"name": name, "workflow_id": workflow_id},
            }
        except Exception as ex:
            return {"creation_mode": "ui_required", "error": str(ex)}

    return {
        "creation_mode": "ui_required",
        "remediation": "Provide ui=NullRunUI() or session_cookie+csrf_token.",
    }


def setup_policy(
    spec: dict,
    *,
    org_id: str,
    workflow_id: str,
    session_cookie: str | None = None,
    csrf_token: str | None = None,
    ui: NullRunUI | None = None,
    ledger: Ledger | None = None,
) -> dict:
    """Create a policy (BUDGET, RATELIMIT, TOOL_BLOCK, etc.). Returns policy_id."""
    spec = {**spec, "workflow_id": workflow_id}

    if session_cookie or csrf_token:
        api = NullRunAPI(
            org_id=org_id,
            session_cookie=session_cookie or "",
            csrf_token=csrf_token or "",
        )
        r = api.create_policy(spec)
        if r["status"] in (200, 201):
            body = r["body"] if isinstance(r["body"], dict) else {}
            pid = body.get("id") or body.get("policy_id")
            if ledger and pid:
                ledger.add("policy", pid, spec)
            return {"creation_mode": "api", "policy_id": pid, "fixture": spec}

    if ui is not None:
        try:
            ui.create_policy_via_ui(workflow_id, spec)
            if ledger:
                ledger.add("policy", "ui-created", spec)
            return {"creation_mode": "ui", "policy_id": "ui-created", "fixture": spec}
        except Exception as ex:
            return {"creation_mode": "ui_required", "error": str(ex)}

    return {"creation_mode": "ui_required", "remediation": "Provide ui= or session_cookie+csrf_token."}


def setup_approval_rule(
    name: str,
    matcher: dict,
    *,
    workflow_id: str,
    org_id: str,
    session_cookie: str | None = None,
    csrf_token: str | None = None,
    ledger: Ledger | None = None,
) -> dict:
    """Create an approval rule bound to a workflow."""
    if not (session_cookie or csrf_token):
        return {"creation_mode": "ui_required", "remediation": "Provide session_cookie+csrf_token."}
    api = NullRunAPI(
        org_id=org_id,
        session_cookie=session_cookie or "",
        csrf_token=csrf_token or "",
    )
    r = api.create_approval_rule(workflow_id, name, matcher)
    if r["status"] in (200, 201):
        body = r["body"] if isinstance(r["body"], dict) else {}
        rid = body.get("id") or body.get("rule_id")
        if ledger and rid:
            ledger.add("approval_rule", rid, {"name": name, "matcher": matcher})
        return {"creation_mode": "api", "rule_id": rid, "fixture": {"name": name, "matcher": matcher}}
    return {"creation_mode": "ui_required", "status": r["status"], "body": str(r["body"])[:200]}


def teardown_workflow(workflow_id: str, *, org_id: str, session_cookie: str | None = None,
                       csrf_token: str | None = None) -> tuple[int, Any]:
    api = NullRunAPI(org_id=org_id, session_cookie=session_cookie or "", csrf_token=csrf_token or "")
    return api.delete_workflow(workflow_id)


def teardown_policy(policy_id: str, *, org_id: str, session_cookie: str | None = None,
                     csrf_token: str | None = None) -> tuple[int, Any]:
    api = NullRunAPI(org_id=org_id, session_cookie=session_cookie or "", csrf_token=csrf_token or "")
    return api.delete_policy(policy_id)


def teardown_api_key(key_id: str, *, org_id: str, session_cookie: str | None = None,
                      csrf_token: str | None = None) -> tuple[int, Any]:
    api = NullRunAPI(org_id=org_id, session_cookie=session_cookie or "", csrf_token=csrf_token or "")
    return api.revoke_api_key(key_id)


def teardown_approval_rule(rule_id: str, *, org_id: str, session_cookie: str | None = None,
                            csrf_token: str | None = None) -> tuple[int, Any]:
    api = NullRunAPI(org_id=org_id, session_cookie=session_cookie or "", csrf_token=csrf_token or "")
    return api.delete_approval_rule(rule_id)


__all__ = [
    "NullRunAPI",
    "NullRunUI",
    "Ledger",
    "setup_workflow_with_budget",
    "setup_api_key",
    "setup_policy",
    "setup_approval_rule",
    "teardown_workflow",
    "teardown_policy",
    "teardown_api_key",
    "teardown_approval_rule",
]
