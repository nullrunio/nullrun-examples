"""TC-22: chain org mismatch — cross-org chain_id should be rejected."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "chain_started": "CHAIN_STARTED" in stdout,
        "cross_org_rejected": "CROSS_ORG_GATE_FAIL" in stdout,
        "cross_org_ok_returned": "CROSS_ORG_GATE_OK" in stdout,
        "cross_org_error_code": None,
        "cross_org_status": None,
        "verdict": "ERROR",
    }
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/gate" in url and c.get("method") == "POST":
                    f["cross_org_status"] = str(c.get("response_status"))
                    resp = c.get("response") or {}
                    if isinstance(resp, dict):
                        ec = resp.get("error_code") or (resp.get("details") or {}).get("error_code")
                        if ec:
                            f["cross_org_error_code"] = ec
        except Exception:
            pass
    # PASS conditions:
    # 1. Server returns 4xx with ORG_MISMATCH/CHAIN_ORG_MISMATCH (cross-org rejected at wire level)
    # 2. SDK raises typed exception (NullRunChainError) — even better
    org_mismatch_codes = {"ORG_MISMATCH", "CHAIN_ORG_MISMATCH", "CHAIN_CROSS_ORG"}
    if f["cross_org_status"] in ("403", "422") and f["cross_org_error_code"] in org_mismatch_codes:
        f["verdict"] = "PASS"
    elif f["cross_org_rejected"] and f["cross_org_status"] in ("403", "422"):
        f["verdict"] = "PASS"
    elif f["cross_org_ok_returned"] and f["cross_org_status"] in ("403", "422"):
        # SDK returned a dict but wire shows 403 ORG_MISMATCH → block path
        f["verdict"] = "PASS"
    elif f["cross_org_ok_returned"]:
        # Server returned 200 with cross-org chain_id — security regression!
        f["verdict"] = "BLOCK"
    else:
        f["verdict"] = "REVIEW"
    return f


def evidence(ui, wf_id, key, stdout, dump_path):
    ev = {"api_key_shape": key.startswith("nr_live_")}
    if dump_path and dump_path.exists():
        try:
            ev["wire_exchanges"] = len(json.loads(dump_path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return ev


if __name__ == "__main__":
    rc = run_tc(22, "chain_mismatch", runner_path=EXAMPLES / "_tc22_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
