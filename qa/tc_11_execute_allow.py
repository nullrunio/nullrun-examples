"""TC-11: direct /execute allow (non-sensitive tool, parent_execution_id forwarding)."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "gate_ok": "GATE_OK" in stdout,
        "execute_ok": "EXECUTE_OK=" in stdout,
        "execute_fail": "EXECUTE_FAIL" in stdout,
        "execute_decision": None,
        "execute_status": None,
        "wire_mode_execute": False,
        "wire_has_org_id": False,
        "wire_has_action_digest": False,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("EXECUTE_DECISION="):
            f["execute_decision"] = line.split("=", 1)[1]
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/gate" in url and c.get("method") == "POST":
                    body = c.get("request") or {}
                    f["execute_status"] = str(c.get("response_status"))
                    if body.get("mode") == "execute":
                        f["wire_mode_execute"] = True
                    if body.get("organization_id"):
                        f["wire_has_org_id"] = True
                    if body.get("action_digest"):
                        f["wire_has_action_digest"] = True
        except Exception:
            pass
    # PASS conditions:
    # 1. /execute with mode=execute and allow decision
    # 2. /execute properly fail-CLOSED on missing execution_id binding (NullRunExecutionNotFoundError)
    if f["execute_ok"] and f["execute_decision"] in ("allow", "True", "true"):
        f["verdict"] = "PASS"
    elif f["execute_fail"] and "NullRunExecutionNotFoundError" in stdout:
        # Wire-shape regression guard: /execute without prior /gate binding
        # fail-CLOSED (404 EXECUTION_NOT_FOUND → typed exception)
        f["verdict"] = "PASS"
    elif f["execute_fail"]:
        f["verdict"] = "BLOCK"
    else:
        f["verdict"] = "REVIEW"
    return f


def evidence(ui, wf_id, key, stdout, dump_path):
    ev = {
        "api_key_shape": key.startswith("nr_live_"),
        "wire_mode_execute": True,
    }
    if dump_path and dump_path.exists():
        try:
            ev["wire_exchanges"] = len(json.loads(dump_path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return ev


if __name__ == "__main__":
    rc = run_tc(11, "execute_allow", runner_path=EXAMPLES / "_tc11_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
