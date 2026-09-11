"""TC-7: /cancel — in-flight execution cancellation (8-step)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qa._driver_template import run_tc, EXAMPLES


def parse(stdout: str, dump_path):
    findings = {
        "server_exec_id_present": "SERVER_EXEC_ID=" in stdout,
        "cancel_invoked": "CANCEL_RESULT=" in stdout,
        "cancel_failed": "CANCEL_FAIL" in stdout,
        "cancel_status": None,
        "cancel_url": None,
        "cancel_request_has_exec_id": False,
        "verdict": "ERROR",
    }
    if not dump_path or not dump_path.exists():
        return findings
    try:
        captures = json.loads(dump_path.read_text(encoding="utf-8"))
    except Exception:
        return findings
    for c in captures:
        url = c.get("url", "")
        if url.endswith("/api/v1/cancel"):
            findings["cancel_url"] = url
            findings["cancel_status"] = str(c.get("response_status"))
            req = c.get("request") or {}
            findings["cancel_request_has_exec_id"] = bool(req.get("execution_id"))
            break
    # Verdict: cancel status 200 + execution_id present in request
    if findings["cancel_status"] == "200" and findings["cancel_request_has_exec_id"]:
        findings["verdict"] = "PASS"
    elif findings["cancel_failed"]:
        findings["verdict"] = "BLOCK"
    elif findings["cancel_status"] and findings["cancel_status"] != "200":
        findings["verdict"] = "BLOCK"
        findings["block_reason"] = f"cancel status {findings['cancel_status']}"
    else:
        findings["verdict"] = "REVIEW"
    return findings


def evidence(ui, wf_id, key, stdout, dump_path):
    ev = {"api_key_shape": key.startswith("nr_live_")}
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            ev["wire_exchanges"] = len(captures)
            ev["cancel_captured"] = any(
                c.get("url", "").endswith("/api/v1/cancel") for c in captures
            )
        except Exception as ex:
            ev["dump_error"] = str(ex)
    return ev


if __name__ == "__main__":
    rc = run_tc(
        tc_number=7,
        tc_name="cancel",
        runner_path=EXAMPLES / "_tc7_runner.py",
        policy_setup=None,
        verdict_parser=parse,
        evidence_collector=evidence,
    )
    sys.exit(rc)
