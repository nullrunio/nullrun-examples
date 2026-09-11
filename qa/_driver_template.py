"""Reusable 8-step driver template for TC-7..TC-30.

Wraps the common Playwright dance (login → workflow → api-key → env →
runner → parse → evidence → teardown) and accepts TC-specific
callbacks for the variable parts:

  policy_setup(ui, wf_id, api)        — STEP 2: create policy/approval_rule/etc.
  probe_runner(plain_key)              — STEP 5: return (returncode, stdout, dump_path)
  verdict_parser(stdout, dump_path)    — STEP 6: return dict of findings
  evidence_collector(ui, wf_id, key, stdout, dump_path) — STEP 7: return dict

Each TC driver is a thin file that subclasses TCDriver (or calls
run_tc(...) directly) with its specific bits. The big wins:

  - no duplicated login/teardown code
  - consistent 8-step pattern across all 25 TCs
  - TC-specific failure modes surface in the verdict

For each TC: ``python qa/tc_N_xxx.py`` produces a self-contained report.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# UTF-8 stdout
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

EXAMPLES = ROOT / "examples"
QA = ROOT / "qa"


# ---------------------------------------------------------------------------
# STEP 0 — Login
# ---------------------------------------------------------------------------
def step0_login() -> dict:
    """Login as scalejohn via Playwright. Returns {'ui': ..., 'session_cookie': ...}."""
    from qa.setup_helpers import NullRunUI
    ui = NullRunUI(headless=True)
    ui._ensure_browser()
    ui._page.goto("https://nullrun.io/login", wait_until="networkidle", timeout=60000)
    ui._page.fill('input[name="login-email"]', "redacted-staging-user@example.test")
    ui._page.fill('input[name="password-secret"]', "REDACTED_STAGING_PASSWORD")
    ui._page.get_by_role("button", name="Sign in").click()
    ui._page.wait_for_url(lambda url: "/login" not in url, timeout=30000)
    return {"ui": ui}


# ---------------------------------------------------------------------------
# STEP 1 — Workflow creation (UI path)
# ---------------------------------------------------------------------------
def step1_create_workflow(ui, name: str) -> str:
    """Create workflow via /control-center/workflows → New workflow. Return wf_id."""
    ui._page.goto("https://nullrun.io/control-center/workflows",
                  wait_until="networkidle", timeout=30000)
    ui._page.get_by_role("button", name="New workflow").click(timeout=15000)
    ui._page.wait_for_selector('input[placeholder="my-workflow"]', timeout=15000)
    ui._page.fill('input[placeholder="my-workflow"]', name)
    ui._page.get_by_role("button", name="Create").click(timeout=15000)
    ui._page.wait_for_timeout(2000)
    open_links = ui._page.locator('a[href*="/control-center/workflows/"]')
    open_links.first.click(timeout=15000)
    ui._page.wait_for_url(
        lambda url: "/workflows/" in url and not url.rstrip("/").endswith("/workflows"),
        timeout=15000,
    )
    wf_id = [seg for seg in ui._page.url.split("/") if len(seg) == 36 and seg.count("-") == 4][0]
    return wf_id


# ---------------------------------------------------------------------------
# STEP 3 — API key creation (UI path)
# ---------------------------------------------------------------------------
def step3_create_api_key(ui, workflow_id: str, name: str, workflow_name: str) -> dict:
    """Create API key bound to workflow. Returns {'plain_key', 'key_id'}."""
    ui._page.goto("https://nullrun.io/control-center/api-keys",
                  wait_until="networkidle", timeout=30000)
    ui._page.get_by_role("button", name="New key").click(timeout=15000)
    ui._page.wait_for_timeout(800)
    name_input = ui._page.query_selector('input[placeholder="prod-primary"]')
    if name_input:
        name_input.fill(name)
    wf_btn = ui._page.query_selector(f'[role="dialog"] button:has-text("{workflow_name}")')
    if wf_btn:
        wf_btn.click(timeout=10000)
    ui._page.get_by_role("button", name="Create Key").click(timeout=15000)
    ui._page.wait_for_timeout(2500)
    plain = ""
    key_span = ui._page.query_selector(
        '[role="dialog"] span.truncate, '
        '[role="dialog"] button[data-testid="copyable-id"]'
    )
    if key_span:
        candidate = (key_span.text_content() or "").strip()
        if candidate.startswith("nr_live_") and " " not in candidate:
            plain = candidate
    if not plain:
        body = ui._page.text_content('[role="dialog"]') or ''
        m = re.search(r'nr_live_[A-Za-z0-9_\-]{20,80}', body)
        if m:
            plain = m.group(0)
    return {"plain_key": plain, "key_id": "ui-created"}


# ---------------------------------------------------------------------------
# STEP 4 — Write .env
# ---------------------------------------------------------------------------
def step4_write_env(plain_key: str, api_url: str = "https://api.nullrun.io") -> Path:
    env_path = EXAMPLES / ".env"
    env_path.write_text(
        f"NULLRUN_API_KEY={plain_key}\n"
        f"NULLRUN_API_URL={api_url}\n"
        "NULLRUN_OPENAI_API_KEY=sk-test-doesnt-matter\n",
        encoding="utf-8",
    )
    return env_path


# ---------------------------------------------------------------------------
# STEP 5 — Run probe via runner script (subprocess)
# ---------------------------------------------------------------------------
def step5_run_probe_via_runner(runner_path: Path) -> dict:
    """Subprocess the runner script. Returns {'returncode', 'stdout', 'stderr'}."""
    proc = subprocess.run(
        [sys.executable, "-u", str(runner_path)],
        cwd=str(EXAMPLES),
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


# ---------------------------------------------------------------------------
# STEP 8 — Teardown (FK-safe: api-key → workflow)
# ---------------------------------------------------------------------------
def step8_teardown(ui, workflow_id: str) -> dict:
    actions = []
    try:
        ui._page.goto("https://nullrun.io/control-center/api-keys",
                      wait_until="networkidle", timeout=30000)
        actions.append("api-key-list-opened")
    except Exception as e:
        actions.append(f"api-key-list-error: {e}")
    try:
        ui._page.goto(f"https://nullrun.io/control-center/workflows/{workflow_id}",
                      wait_until="networkidle", timeout=30000)
        actions.append("workflow-detail-opened")
    except Exception as e:
        actions.append(f"workflow-detail-error: {e}")
    return {"actions": actions}


# ---------------------------------------------------------------------------
# Driver entry point
# ---------------------------------------------------------------------------
def run_tc(
    tc_number: int,
    tc_name: str,
    *,
    runner_path: Path,
    policy_setup: Callable | None = None,
    verdict_parser: Callable,
    evidence_collector: Callable,
    workflow_name_prefix: str | None = None,
) -> int:
    """Execute one full 8-step TC driver. Returns exit code (0=PASS, 1≠PASS)."""
    RUN_ID = os.environ.get("RUN_ID", time.strftime("%Y%m%dT%H%M%S"))
    wfp = workflow_name_prefix or f"TC{tc_number}"
    name = f"{wfp}-{RUN_ID}-{uuid.uuid4().hex[:6]}"
    print(f"=== TC-{tc_number} ({tc_name}) RUN_ID={RUN_ID} name={name} ===")

    created = {"workflow_id": None, "plain_key": None}
    verdict = "ERROR"
    ui = None
    try:
        ui = step0_login()["ui"]

        # STEP 1 — Workflow
        print("\n[STEP 1] Create workflow …")
        wf_id = step1_create_workflow(ui, name)
        created["workflow_id"] = wf_id
        print(f"  workflow_id={wf_id}")

        # STEP 2 — Policy (TC-specific)
        if policy_setup is not None:
            print("\n[STEP 2] Setup policy/approval_rule …")
            try:
                setup_result = policy_setup(ui, wf_id, name)
                print(f"  setup: {setup_result}")
            except Exception as ex:
                print(f"  policy_setup failed: {ex}")
                setup_result = {"status": "failed", "error": str(ex)}
        else:
            print("\n[STEP 2] (no policy setup — using workflow defaults)")

        # STEP 3 — API key
        print("\n[STEP 3] Create API key …")
        key = step3_create_api_key(ui, wf_id, f"{name}-key", workflow_name=name)
        created["plain_key"] = key["plain_key"]
        if key["plain_key"]:
            print(f"  plain_key={key['plain_key'][:24]}…")
        else:
            print("  WARN: plain_key not extracted")

        # STEP 4 — .env
        print("\n[STEP 4] Write examples/.env …")
        if key["plain_key"]:
            env_path = step4_write_env(key["plain_key"])
            print(f"  env_path={env_path}")

        # STEP 5 — Run probe via runner
        if not runner_path.exists():
            print(f"\n[STEP 5] SKIPPED — runner file missing: {runner_path}")
            result = {"returncode": -1, "stdout": "", "stderr": "runner file missing"}
        elif not key["plain_key"]:
            print("\n[STEP 5] SKIPPED — no api_key")
            result = {"returncode": -1, "stdout": "", "stderr": "no api_key"}
        else:
            print(f"\n[STEP 5] Run {_path_basename(runner_path)} …")
            result = step5_run_probe_via_runner(runner_path)
            print(f"  returncode: {result['returncode']}")
            print(f"  stdout length: {len(result['stdout'])} chars, {len(result['stdout'].splitlines())} lines")
            print(f"  stdout (full):")
            for line in result["stdout"].splitlines():
                print(f"    {line}")
            if result["stderr"]:
                print(f"  stderr: {result['stderr'][:500]}")

        # STEP 6 — Parse verdict
        print("\n[STEP 6] Parse findings …")
        dump_path = runner_path.parent / f"_tc{tc_number}_wire_dump.json"
        findings = verdict_parser(result["stdout"], dump_path if dump_path.exists() else None)
        for k, v in findings.items():
            print(f"  {k}: {v}")

        verdict = findings.get("verdict", "ERROR")
        if verdict == "PASS":
            print("  ✅ PASS")
        elif verdict == "BLOCK":
            print(f"  ❌ BLOCK: {findings.get('block_reason', '?')}")
        else:
            print(f"  ⚠️  {verdict}: {findings.get('reason', '')}")

        # STEP 7 — Evidence
        print("\n[STEP 7] Gather evidence …")
        try:
            ev = evidence_collector(ui, wf_id, key["plain_key"] or "", result["stdout"], dump_path if dump_path.exists() else None)
            for k, v in ev.items():
                print(f"  {k}: {v}")
        except Exception as ex:
            print(f"  evidence_collector failed: {ex}")

    except Exception as e:
        print(f"\n[EXCEPTION] {type(e).__name__}: {e}")
        verdict = "ERROR"
        raise
    finally:
        # STEP 8 — Teardown
        print("\n[STEP 8] Teardown …")
        if ui is not None and created["workflow_id"]:
            try:
                td = step8_teardown(ui, created["workflow_id"])
                for a in td["actions"]:
                    print(f"  {a}")
            except Exception as e:
                print(f"  teardown error: {e}")
        if ui is not None:
            try:
                ui.close()
            except Exception:
                pass

    print(f"\n=== TC-{tc_number} END verdict={verdict} ===")
    return 0 if verdict == "PASS" else 1


def _path_basename(p: Path) -> str:
    return p.name
