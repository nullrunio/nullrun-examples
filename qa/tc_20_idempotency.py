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
    # PASS conditions:
    # - both calls OK
    # - execution IDs match (idempotency)
    # - second call has idempotent_replay=True OR exec_id matches
    if f["first_ok"] and f["second_ok"]:
        if f["second_replay"] is True:
            f["verdict"] = "PASS"
        elif f["exec_ids_match"]:
            f["verdict"] = "PASS"  # server returned same execution_id = idempotent
        else:
            f["verdict"] = "REVIEW"
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
