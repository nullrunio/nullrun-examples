"""TC-20: /gate idempotency — same operation_id → second call returns idempotent_replay=true."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "first_ok": "FIRST_OK=" in stdout,
        "second_ok": "SECOND_OK=" in stdout,
        "first_fail": "FIRST_FAIL" in stdout,
        "second_fail": "SECOND_FAIL" in stdout,
        "first_decision": None,
        "second_decision": None,
        "first_exec_id": None,
        "second_exec_id": None,
        "second_replay": None,
        "exec_ids_match": None,
        "operation_id_echoed": False,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("FIRST_DECISION="):
            f["first_decision"] = line.split("=", 1)[1]
        elif line.startswith("SECOND_DECISION="):
            f["second_decision"] = line.split("=", 1)[1]
        elif line.startswith("FIRST_EXEC_ID="):
            f["first_exec_id"] = line.split("=", 1)[1]
        elif line.startswith("SECOND_EXEC_ID="):
            f["second_exec_id"] = line.split("=", 1)[1]
        elif line.startswith("SECOND_REPLAY="):
            f["second_replay"] = line.split("=", 1)[1].lower() == "true"
    if f["first_exec_id"] and f["second_exec_id"]:
        f["exec_ids_match"] = f["first_exec_id"] == f["second_exec_id"]
    # Check operation_id echoed on both requests (same value)
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            op_ids = []
            for c in captures:
                if "/gate" in c.get("url", "") and c.get("method") == "POST":
                    req = c.get("request") or {}
                    if req.get("operation_id"):
                        op_ids.append(req["operation_id"])
            if len(op_ids) >= 2 and op_ids[0] == op_ids[1]:
                f["operation_id_echoed"] = True
        except Exception:
            pass
    # Verdict logic:
    # - Both calls succeed with operation_id echoed (wire-shape OK)
    # - execution_id match OR idempotent_replay flag = full idempotency
    # - Otherwise REVIEW: wire-shape OK but server doesn't dedupe /gate by operation_id
    if f["first_ok"] and f["second_ok"]:
        if f["operation_id_echoed"]:
            if f["second_replay"] is True or f["exec_ids_match"]:
                f["verdict"] = "PASS"  # full idempotency
            else:
                # Wire shape accepts operation_id but server returns fresh execution_id
                # each call — potential double-charge risk. Surface as defect.
                f["verdict"] = "REVIEW"
        else:
            f["verdict"] = "BLOCK"
    elif f["first_fail"] or f["second_fail"]:
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
    rc = run_tc(20, "idempotency", runner_path=EXAMPLES / "_tc20_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
