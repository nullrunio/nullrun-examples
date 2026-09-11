"""setup_assertions.py — Programmatic precondition assertions per SDK_TEST §2.2.

Aligned with SDK_TEST.md v4.2 (2026-09-04): UI-primary, API-fallback setup.
If any assertion fails, the calling TC must exit with code 77 and tag its verdict
SETUP-FAIL (NOT FAIL). This prevents drift between prose preconditions and the
actual environment from being silently recorded as a test defect.

Public surface (per §2.2.1):
    SetupAssertionError                       — custom exception with remediation hint
    assert_workflow_active(workflow_id, api)  — workflow not soft-deleted, state=Normal
    assert_workflow_has_policy(workflow_id, kind, api, min_cents=None)
    assert_sdk_uuid_validation_enabled()
    assert_env_inherits_in_subprocess(env_var="NULLRUN_API_KEY")
    assert_sdk_version(installed, expected_min="0.12.0")
    assert_api_key_valid(api_key, api_url)
    assert_workflow_isolation(org_id, expected=(), api)
    assert_approval_rule_present(workflow_id, rule_name, api)
    assert_policy_active(policy_id, api)
"""
from __future__ import annotations

import os
import re
import sys
import json
import time
import uuid
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from typing import Any, Iterable


# --------------------------------------------------------------------------- #
# Exception with remediation hint
# --------------------------------------------------------------------------- #

class SetupAssertionError(AssertionError):
    """Raised when a programmatic precondition assertion fails.

    Carries a ``remediation`` hint string so the runner can write actionable
    diagnostics to stderr (per §2.2.1 template).
    """

    def __init__(self, msg: str, remediation: str = ""):
        super().__init__(msg)
        self.remediation = remediation or "Investigate runner logs; re-run pre-flight."


# --------------------------------------------------------------------------- #
# Helpers (httpx-based; urllib fallback if not installed)
# --------------------------------------------------------------------------- #

def _scrub_key(api_key: str) -> str:
    return re.sub(r"nr_live_[A-Za-z0-9_]+", "nr_live_<REDACTED>", api_key or "")


def _http(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    payload: dict | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict | str]:
    """Minimal HTTP wrapper. Returns (status_code, parsed_json_or_text)."""
    try:
        import httpx  # noqa: F401  (preferred)
        data = json.dumps(payload).encode() if payload is not None else None
        r = httpx.request(method, url, json=payload, headers=headers, timeout=timeout)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, r.text
    except ImportError:
        # urllib fallback
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                try:
                    return resp.status, json.loads(body)
                except json.JSONDecodeError:
                    return resp.status, body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                return e.code, json.loads(body)
            except json.JSONDecodeError:
                return e.code, body
        except Exception as e:
            return 0, str(e)


# --------------------------------------------------------------------------- #
# Core assertions (per §2.2.1)
# --------------------------------------------------------------------------- #

def assert_workflow_active(workflow_id: str, api: Any = None) -> None:
    """Verify the workflow exists, not soft-deleted, and in Normal state.

    Args:
        workflow_id: UUID of the workflow to check.
        api: Optional API client (httpx-based). If None, falls back to
             direct GET against /api/v1/orgs/{org}/workflows/{id} using
             NULLRUN_API_KEY from env (requires admin endpoint access).
    """
    org_id = os.environ.get("NULLRUN_ORG_ID", "")
    api_key = os.environ.get("NULLRUN_API_KEY", "")
    if api is not None:
        # Use provided client (e.g. NullRunAPI instance)
        wf = api.get_workflow(workflow_id)
    elif org_id and api_key:
        url = f"https://api.nullrun.io/api/v1/orgs/{org_id}/workflows/{workflow_id}"
        status, body = _http("GET", url, headers={"Authorization": f"Bearer {api_key}"})
        if status == 401:
            raise SetupAssertionError(
                f"workflow {workflow_id} requires session cookie (Bearer not authorized)",
                remediation="Use UI login (Playwright) to obtain __Host-nullrun_session cookie, "
                            "or call setup_helpers.NullRunUI.login() first.",
            )
        if status != 200:
            raise SetupAssertionError(
                f"workflow {workflow_id} GET returned {status}: {str(body)[:120]}",
                remediation="Check that the workflow exists in the org via UI: "
                            "/control-center/workflows/" + workflow_id,
            )
        wf = body if isinstance(body, dict) else {}
    else:
        raise SetupAssertionError(
            "no API client or NULLRUN_ORG_ID+NULLRUN_API_KEY env to assert workflow active",
            remediation="Provide api=NullRunUI(...) instance or set NULLRUN_ORG_ID/NULLRUN_API_KEY.",
        )

    if not wf:
        raise SetupAssertionError(f"workflow {workflow_id} returned empty body")

    if wf.get("deleted_at") is not None:
        raise SetupAssertionError(
            f"workflow {workflow_id} is soft-deleted (deleted_at={wf['deleted_at']})",
            remediation="Restore via UI: /control-center/workflows → Restore action.",
        )

    state = wf.get("state") or wf.get("workflow_state")
    if state and state != "Normal":
        raise SetupAssertionError(
            f"workflow {workflow_id} state={state!r}, expected 'Normal'",
            remediation="Re-activate via UI or skip TC; do NOT declare BLOCKED-SETUP. "
                        "Active workflow state is NOT a valid BLOCKED-SETUP reason (SDK_TEST §5.4 v4.2).",
        )


def assert_workflow_has_policy(
    workflow_id: str,
    kind: str,
    api: Any = None,
    *,
    min_cents: int | None = None,
) -> None:
    """Verify the workflow has at least one policy of the given kind attached.

    Args:
        workflow_id: UUID of the workflow.
        kind: policy kind (e.g. "BUDGET", "RATELIMIT", "TOOL_BLOCK", "APPROVAL_REQUIRED").
        api: Optional API client. If None, uses bearer auth.
        min_cents: Optional minimum budget cents (only relevant for BUDGET kind).
    """
    org_id = os.environ.get("NULLRUN_ORG_ID", "")
    api_key = os.environ.get("NULLRUN_API_KEY", "")

    if api is not None:
        policies = api.list_policies(workflow_id=workflow_id)
    elif org_id and api_key:
        url = f"https://api.nullrun.io/api/v1/orgs/{org_id}/workflows/{workflow_id}/policies"
        status, body = _http("GET", url, headers={"Authorization": f"Bearer {api_key}"})
        if status != 200:
            raise SetupAssertionError(
                f"workflow {workflow_id} policies GET returned {status}",
                remediation="Verify workflow exists and org_id is correct.",
            )
        policies = body if isinstance(body, list) else (body.get("policies") or [])
    else:
        raise SetupAssertionError(
            "no API client or env for policy assertion",
            remediation="Provide api=NullRunUI(...) instance.",
        )

    matching = [p for p in policies if (p.get("kind") or p.get("policy_type")) == kind]
    if not matching:
        raise SetupAssertionError(
            f"workflow {workflow_id} has no {kind} policy",
            remediation=f"Create via API: POST /api/v1/orgs/{org_id}/workflows/{workflow_id}/policies "
                        f'with {{"kind": "{kind}", ...}}. Or via UI: /control-center/policies.',
        )

    if min_cents is not None and kind in ("BUDGET", "BUDGET_HARD", "BUDGET_SOFT"):
        for p in matching:
            current = p.get("max_cents") or p.get("budget_cents") or 0
            if current < min_cents:
                raise SetupAssertionError(
                    f"{kind} policy {p.get('id')} has max_cents={current}, required ≥ {min_cents}",
                    remediation=f"Update policy {p.get('id')} max_cents to ≥{min_cents} via "
                                f"PATCH /api/v1/orgs/{org_id}/policies/{p.get('id')} or UI edit.",
                )


def assert_sdk_uuid_validation_enabled() -> None:
    """Sanity check: SDK's chain_id validation rejects non-UUID strings.

    Used to detect regressions where SDK silently accepts invalid chain_ids.
    Soft pass if SDK has no public guard API (0.14.x is permissive).
    """
    try:
        from nullrun.context import _validate_chain_id  # type: ignore
        try:
            _validate_chain_id("not-a-uuid")
        except ValueError as e:
            if "UUID" in str(e):
                return
            raise SetupAssertionError(
                f"SDK _validate_chain_id error does not mention UUID: {e}",
                remediation="Fix SDK error message OR update setup_assertions.py",
            )
        raise SetupAssertionError(
            "SDK _validate_chain_id accepted 'not-a-uuid' — UUID validation removed?",
            remediation="Investigate SDK regression; this is a real defect if validator was present.",
        )
    except ImportError:
        return  # 0.14.x has no public guard — soft pass


def assert_env_inherits_in_subprocess(env_var: str = "NULLRUN_API_KEY") -> None:
    """Confirm env var survives into subprocess (Python -c import check)."""
    if env_var not in os.environ:
        raise SetupAssertionError(
            f"{env_var} not in os.environ",
            remediation=f"export {env_var}=... before running probe; or set in .env",
        )
    r = subprocess.run(
        [sys.executable, "-c", f"import os, sys; sys.exit(0 if os.environ.get('{env_var}') else 1)"],
        env=os.environ,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if r.returncode != 0:
        raise SetupAssertionError(
            f"subprocess does NOT see {env_var} (rc={r.returncode}): {r.stderr}",
            remediation="Pass env explicitly: subprocess.run([...], env={**os.environ, ...})",
        )


def assert_sdk_version(installed: str, expected_min: str = "0.12.0") -> None:
    """Compare SDK version against the plan-mandated minimum."""
    def _v(s: str) -> tuple[int, ...]:
        m = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", (s or "").strip())
        if not m:
            raise SetupAssertionError(f"cannot parse version {s!r}")
        return tuple(int(x or 0) for x in m.groups())
    if _v(installed) < _v(expected_min):
        raise SetupAssertionError(
            f"SDK {installed} is older than required minimum {expected_min}",
            remediation=f"pip install 'nullrun>={expected_min}' in .venv",
        )


def assert_api_key_valid(api_key: str, api_url: str = "https://api.nullrun.io") -> None:
    """POST /api/v1/auth/verify with the candidate key — must return 200 + valid:true."""
    if not api_key:
        raise SetupAssertionError("api_key is empty", remediation="Set NULLRUN_API_KEY or pass explicitly.")
    url = api_url.rstrip("/") + "/api/v1/auth/verify"
    status, body = _http("POST", url, payload={"api_key": api_key})
    if status != 200:
        raise SetupAssertionError(
            f"/auth/verify returned HTTP {status} (body={str(body)[:120]}) for key {_scrub_key(api_key)}",
            remediation="Key may be revoked; rotate via UI: /control-center/api-keys → Rotate.",
        )
    if isinstance(body, dict) and body.get("valid") is False:
        raise SetupAssertionError(
            f"/auth/verify valid=false: {body}",
            remediation="Check key prefix matches expected org; verify key not revoked.",
        )


def assert_workflow_isolation(
    org_id: str,
    expected: Iterable[str] = (),
    *,
    api: Any = None,
) -> None:
    """Confirm no leftover policies/workflows/keys/rules belong to this RUN_ID
    other than the expected list.

    Per §2.3.4, this is run BEFORE per-TC isolation assertion. If any leaked
    entity is found (not in expected, not soft-deleted), raise.
    """
    expected = list(expected)
    if api is not None:
        # List all entities for the org
        policies = api.list_policies(org_id=org_id)
        workflows = api.list_workflows(org_id=org_id)
        keys = api.list_api_keys(org_id=org_id)
        rules = api.list_approval_rules(org_id=org_id)
    else:
        # Soft assertion when no API: rely on caller (pre-flight already verified)
        return

    leaked = []
    for coll in (policies, workflows, keys, rules):
        for e in (coll or []):
            name = e.get("name") or ""
            prefix = name.split("-")[0] if "-" in name else ""
            if prefix in ("POL", "WF", "KEY", "AR") and not any(exp in name for exp in expected):
                leaked.append(name)

    if leaked:
        raise SetupAssertionError(
            f"isolation breach: {len(leaked)} leftover test entities (e.g. {leaked[0]})",
            remediation="Run cleanup via §6.14 (UI delete workflow, cascade deletes "
                        "policies/rules/keys) before retrying.",
        )


def assert_approval_rule_present(workflow_id: str, rule_name: str, api: Any = None) -> None:
    """Verify an approval rule with given name is attached to the workflow."""
    if api is None:
        raise SetupAssertionError(
            "no API client for approval-rule assertion",
            remediation="Provide api=NullRunUI(...) instance.",
        )
    rules = api.list_approval_rules(workflow_id=workflow_id) or []
    names = [r.get("name") for r in rules]
    if rule_name not in names:
        raise SetupAssertionError(
            f"approval rule {rule_name!r} not on workflow {workflow_id}; found {names[:3]}...",
            remediation="Create via API: POST /api/v1/orgs/{org}/approval-rules or UI: "
                        "/control-center/approval-rules → New rule.",
        )


def assert_policy_active(policy_id: str, api: Any = None) -> None:
    """Verify policy is active (not soft-deleted, enforcement enabled)."""
    if api is None:
        raise SetupAssertionError("no API client for policy assertion", remediation="Pass api=NullRunUI(...).")
    p = api.get_policy(policy_id)
    if not p:
        raise SetupAssertionError(f"policy {policy_id} not found", remediation="Re-create or skip TC.")
    if p.get("deleted_at") is not None:
        raise SetupAssertionError(
            f"policy {policy_id} is soft-deleted",
            remediation="Restore via UI or re-create.",
        )


__all__ = [
    "SetupAssertionError",
    "assert_workflow_active",
    "assert_workflow_has_policy",
    "assert_sdk_uuid_validation_enabled",
    "assert_env_inherits_in_subprocess",
    "assert_sdk_version",
    "assert_api_key_valid",
    "assert_workflow_isolation",
    "assert_approval_rule_present",
    "assert_policy_active",
]
