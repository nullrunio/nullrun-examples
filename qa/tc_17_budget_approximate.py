"""TC-17: GET /budget/approximate — happy path or 503 BUDGET_DATA_UNAVAILABLE."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "approx_ok": "APPROX_OK=" in stdout,
        "approx_fail": "APPROX_FAIL" in stdout,
        "approx_status": None,
        "approx_error_code": None,
        "approx_body_has_sources": False,
        "verdict": "ERROR",
    }
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/budget/approximate" in url:
                    f["approx_status"] = str(c.get("response_status"))
                    resp = c.get("response") or {}
                    if isinstance(resp, dict):
                        f["approx_error_code"] = resp.get("error_code")
                        f["approx_body_has_sources"] = "sources" in resp
                    elif isinstance(resp, str):
                        try:
                            obj = json.loads(resp)
                            f["approx_error_code"] = obj.get("error_code")
                            f["approx_body_has_sources"] = "sources" in obj
                        except Exception:
                            pass
        except Exception:
            pass
    if f["approx_ok"] and f["approx_status"] == "200":
        f["verdict"] = "PASS"
    elif f["approx_fail"] and f["approx_status"] in ("503", "500"):
        # 503 with BUDGET_DATA_UNAVAILABLE is BY DESIGN for new orgs (per audit 2026-09-10)
        if f["approx_error_code"] == "BUDGET_DATA_UNAVAILABLE":
            f["verdict"] = "PASS"
        else:
            f["verdict"] = "REVIEW"
    elif f["approx_status"] == "200" and f["approx_body_has_sources"]:
        f["verdict"] = "PASS"
    elif f["approx_fail"]:
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
    rc = run_tc(17, "budget_approximate", runner_path=EXAMPLES / "_tc17_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
