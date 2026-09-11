"""TC-19: /audit-log/verify (hash chain) + /audit-log/export (job create)."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "verify_ok": "AUDIT_VERIFY=" in stdout,
        "verify_fail": "AUDIT_VERIFY_FAIL" in stdout,
        "export_ok": "AUDIT_EXPORT=" in stdout,
        "export_fail": "AUDIT_EXPORT_FAIL" in stdout,
        "verify_status": None,
        "export_status": None,
        "export_job_id": None,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("AUDIT_EXPORT_JOB_ID="):
            f["export_job_id"] = line.split("=", 1)[1]
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/audit-log/verify" in url:
                    f["verify_status"] = str(c.get("response_status"))
                elif "/audit-log/export" in url and "status" not in url:
                    f["export_status"] = str(c.get("response_status"))
        except Exception:
            pass
    # Both endpoints returned 200 → PASS
    if f["verify_status"] == "200" and f["export_status"] in ("200", "201", "202"):
        f["verdict"] = "PASS"
    elif f["verify_fail"] and f["export_fail"]:
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
    rc = run_tc(19, "audit_verify_export", runner_path=EXAMPLES / "_tc19_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
