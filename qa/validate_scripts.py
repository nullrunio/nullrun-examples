"""
validate_scripts.py — catalogue-level script linter.

Scans every test-case script referenced in SDK_TEST_v2 §6 and verifies
the script exists, parses as Python, and exposes a callable `main()`
or has an `if __name__ == "__main__"` block. This is the "all scripts
exist" check from §2 preflight #10 in a deeper form.

Exit codes:
  0  — all referenced scripts validate
  77 — one or more scripts missing or unparseable
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

QA_ROOT = Path(__file__).resolve().parent
EXAMPLES_ROOT = QA_ROOT.parent / "examples"


# (TC id, relative path under nullrun-examples/)
SCRIPT_REFS: list[tuple[str, str]] = [
    # §6.1 SDK Init
    ("TC-SDKF-001", "examples/smoke_test.py"),
    ("TC-SDKF-002", "examples/_env.py"),
    # §6.3 API keys
    ("TC-SDKK-001", "qa/probes/api_key_mask.py"),
    ("TC-SDKK-007", "qa/probes/api_key_mask.py"),
    # §6.5.1 ToolBlock
    ("TC-SDKTB-001", "qa/probes/probe_tb_S07.py"),
    ("TC-SDKTB-005", "src/proxy/http/gate/internal.rs"),  # static
    # §6.5.2 Rate
    ("TC-SDKR-001", "qa/probes/probe_rate_burst.py"),
    ("TC-SDKR-002", "qa/probes/probe_rate_burst_nollm.py"),
    ("TC-SDKR-003", "qa/probes/probe_rate_burst_two_keys.py"),
    # §6.5.3 Budget
    ("TC-SDKB-001", "examples/cost_cap_demo.py"),
    ("TC-SDKB-002", "examples/chain_soft_mode.py"),
    ("TC-SDKB-005", "examples/langgraph_openai_enforcement_gaps_demo.py"),
    # §6.5.4 Approval
    ("TC-SDKA-001", "qa/approval_rules/ar_toolname_run.py"),
    ("TC-SDKA-002", "qa/approval_rules/ar_toolname_run_chain.py"),
    ("TC-SDKA-003", "qa/approval_rules/ar_params_run.py"),
    ("TC-SDKA-004", "qa/approval_rules/ar_threshold_run.py"),
    ("TC-SDKA-005", "qa/approval_rules/ar_dnf_run.py"),
    ("TC-SDKA-006", "examples/langgraph_openai_mcp_demo.py"),
    # §6.5.5 User flow
    ("TC-SDKU-001", "examples/policy_edit_mid_chain.py"),
    ("TC-SDKU-003", "examples/policy_precedence.py"),
    ("TC-SDKU-004", "examples/policy_composite.py"),
    ("TC-SDKU-008", "examples/ar_model_filter.py"),
    ("TC-SDKU-015", "examples/ar_action_digest.py"),
    ("TC-SDKU-010", "examples/ar_multi_rule.py"),
    # §6.5.6 Advanced
    ("TC-SDKU-023", "examples/loop_detection_run.py"),
    ("TC-SDKU-024", "examples/anomaly_mode_run.py"),
    ("TC-SDKU-026", "examples/mcp_umbrella_run.py"),
    ("TC-SDKU-031", "examples/rate_limit_column_run.py"),
    # §6.6 /track
    # §6.7 /execute
    # §6.8 Idempotency
    ("TC-SDKI-003", "qa/probes/edge_net_retry.py"),
    # §6.9 Chain
    ("TC-SDKC-005", "qa/probes/edge_par_chain.py"),
    ("TC-SDKC-006", "qa/probes/edge_inv_chain.py"),
    # §6.10 Load
    ("TC-SDKL-001", "qa/probes/probe_load_check.py"),
    # §6.13 SDK 0.16.5
    ("TC-WS-001", "examples/ws_connect.py"),
    ("TC-WS-006", "examples/ws_graceful_close.py"),
    ("TC-CBWAL-001", "examples/cb_open.py"),
    ("TC-ACT-003", "examples/webhook_backoff.py"),
    ("TC-SDKF-003", "qa/probes/sdk_no_apikey.py"),
    ("TC-SDKF-005", "examples/on_error_hook.py"),
]


def validate_script(rel: str) -> tuple[bool, str]:
    """Validate one script — exists, parses, has main entrypoint or function."""
    # rel is already relative to nullrun-examples/ (e.g. "qa/probes/X.py",
    # "examples/Y.py") OR to NULLRUN repo for .rs static refs.
    nullrun_root = Path("C:/Users/Anatolii Maltsev/Documents/AGENTIC/NULLRUN")
    if rel.startswith("qa/") or rel.startswith("examples/"):
        p = QA_ROOT.parent / rel  # nullrun-examples/{qa,examples}/...
    elif rel.endswith(".rs"):
        p = nullrun_root / rel
    else:
        return False, "unknown-prefix"
    if not p.exists():
        return False, "missing"
    if p.suffix == ".rs":
        return True, "static-rs"
    if p.suffix == ".py":
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
            ast.parse(src)
        except SyntaxError as e:
            return False, f"parse-error: {e}"
        if "__name__" in src or "def main" in src:
            return True, "ok"
        return False, "no main / __main__"
    return True, "unknown"


def main() -> int:
    nullrun_root = Path("C:/Users/Anatolii Maltsev/Documents/AGENTIC/NULLRUN")
    rows: list[tuple[str, str, str]] = []
    failed = 0

    for tc_id, rel in SCRIPT_REFS:
        if rel.startswith("qa/") or rel.startswith("examples/"):
            p = (QA_ROOT.parent / rel) if rel.startswith("examples/") else (QA_ROOT / rel)
        else:
            p = nullrun_root / rel
        ok, status = validate_script(rel)
        marker = "OK" if ok else "FAIL"
        if not ok:
            failed += 1
        rows.append((tc_id, rel, f"{marker} {status}"))

    print(f"validate_scripts.py — {len(SCRIPT_REFS)} script references")
    print("=" * 80)
    for tc, rel, status in rows:
        print(f"  {status:30}  {tc:14}  {rel}")
    print("=" * 80)
    print(f"Failed: {failed}/{len(SCRIPT_REFS)}")
    return 77 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
