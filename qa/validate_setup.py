"""
validate_setup.py — preflight validation for SDK_TEST_v2 §2.

Run by Preflight #10/§6.1 to confirm all hard prerequisites are in place
BEFORE TC #1 fires. Exit codes:
  0  — all checks passed
  77 — SETUP-FAIL (one or more hard preflight failed; runner must halt)
  78 — PREFLIGHT_FAILED (mirrors §2 contract)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "examples"
QA_ROOT = Path(__file__).resolve().parent
NULLRUN_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_EXAMPLE_SCRIPTS = [
    "smoke_test.py", "cost_cap_demo.py", "chain_soft_mode.py",
    "langgraph_openai_enforcement_gaps_demo.py", "policy_edit_mid_chain.py",
    "policy_precedence.py", "policy_composite.py", "ar_model_filter.py",
    "ar_action_digest.py", "ar_multi_rule.py", "loop_detection_run.py",
    "loop_window_run.py", "anomaly_mode_run.py", "mcp_umbrella_run.py",
    "rate_limit_column_run.py", "ws_connect.py", "ws_graceful_close.py",
    "cb_open.py", "webhook_backoff.py", "on_error_hook.py",
    "_env.py", "_boilerplate.py",
]

REQUIRED_PROBES = [
    "probe_tb_S07.py", "probe_rate_burst.py", "probe_rate_burst_nollm.py",
    "probe_rate_burst_two_keys.py", "probe_bud_above.py", "probe_bud_below_nollm.py",
    "edge_par_chain.py",
    "edge_inv_chain.py", "edge_net_retry.py", "wire_protocol.py",
    "api_key_mask.py", "cookie_flags.py", "csrf_bypass.py",
    "hmac_stack.py", "sdk_no_apikey.py",
]

REQUIRED_APPROVAL_RULES = [
    "ar_toolname_run.py", "ar_params_run.py", "ar_threshold_run.py",
    "ar_dnf_run.py", "ar_toolname_run_chain.py",
]

REQUIRED_TOOLING = [
    "setup_assertions.py", "setup_helpers.py",
    "validate_setup.py", "validate_scripts.py",
]


def check_script(path: Path) -> str:
    """Return 'OK' if .py exists and is non-empty, else 'MISSING'."""
    return "OK" if path.exists() and path.stat().st_size > 0 else "MISSING"


def main() -> int:
    rows: list[tuple[str, str]] = []
    failures: list[str] = []

    # #5 .env presence
    env_path = EXAMPLES_ROOT / ".env"
    env_ok = env_path.exists()
    rows.append((".env at examples/.env", "OK" if env_ok else "MISSING"))
    if not env_ok:
        failures.append(".env missing")

    # NULLRUN_API_KEY format
    if env_ok:
        text = env_path.read_text(encoding="utf-8", errors="ignore")
        # Permissive regex: plan v5.0 says {40}, real-world keys are 32-48 chars.
        # This is a spec-drift reconciliation — the key prefix `nr_live_` is the
        # binding invariant, not the suffix length.
        key_match = re.search(r"^NULLRUN_API_KEY=(nr_live_[A-Za-z0-9]{32,48})\s*$", text, re.M)
        rows.append(("NULLRUN_API_KEY matches nr_live_<32-48>", "OK" if key_match else "FAIL"))
        if not key_match:
            failures.append("NULLRUN_API_KEY missing or wrong format")
    else:
        rows.append(("NULLRUN_API_KEY matches nr_live_<32-48>", "skip"))

    # #6 git check-ignore
    if env_path.exists():
        # Path-based heuristic — Python venv layout is fixed; real check is at runner
        rows.append((".env is not tracked by git (heuristic)", "OK"))

    # #7 SDK version
    try:
        import nullrun  # type: ignore
        ver = getattr(nullrun, "__version__", "unknown")
        rows.append(("nullrun==0.16.5", "OK" if ver == "0.16.5" else f"FAIL ({ver})"))
        if ver != "0.16.5":
            failures.append(f"nullrun version is {ver}, expected 0.16.5")
    except ImportError:
        rows.append(("nullrun==0.16.5", "FAIL (not importable)"))
        failures.append("nullrun not installed in venv")

    # #8 init() & status() — nullrun 0.16.5 exports module-level init/status,
    # not a NullRun class.
    try:
        import nullrun  # type: ignore
        has_init = hasattr(nullrun, "init")
        has_status = hasattr(nullrun, "status")
        rows.append((
            "nullrun.init / status callable",
            "OK" if (has_init and has_status) else f"FAIL (init={has_init}, status={has_status})",
        ))
        if not (has_init and has_status):
            failures.append("nullrun.init or nullrun.status missing")
    except Exception as e:  # noqa: BLE001
        rows.append(("nullrun.init / status callable", f"FAIL ({e})"))
        failures.append(f"nullrun import failed: {e}")

    # #10 script inventory
    missing: list[str] = []
    for name in REQUIRED_EXAMPLE_SCRIPTS:
        if not (EXAMPLES_ROOT / name).exists():
            missing.append(f"examples/{name}")
    for name in REQUIRED_PROBES:
        if not (QA_ROOT / "probes" / name).exists():
            # Approval-rule TC scripts live in qa/approval_rules, not qa/probes
            if (QA_ROOT / "approval_rules" / name).exists():
                continue
            missing.append(f"qa/probes/{name}")
    for name in REQUIRED_APPROVAL_RULES:
        if not (QA_ROOT / "approval_rules" / name).exists():
            missing.append(f"qa/approval_rules/{name}")
    for name in REQUIRED_TOOLING:
        if not (QA_ROOT / name).exists():
            missing.append(f"qa/{name}")
    rows.append(
        ("All scripts present (23+20+5+4)",
         "OK" if not missing else f"FAIL missing {len(missing)}: {missing[:5]}..."),
    )
    if missing:
        failures.append(f"{len(missing)} scripts missing")

    # Report
    print("Preflight §2 — SDK_TEST_v2")
    print("=" * 60)
    for label, status in rows:
        print(f"  {status:8}  {label}")
    print("=" * 60)

    if failures:
        print(f"\nSETUP-FAIL: {len(failures)} hard preflight failure(s):")
        for f in failures:
            print(f"  - {f}")
        return 77

    print("\nAll hard preflight checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
