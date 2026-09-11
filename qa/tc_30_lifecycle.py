"""TC-30: SDK lifecycle — init → shutdown → re-init round-trip."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "init_1_ok": "LIFECYCLE_INIT_1" in stdout,
        "shutdown_ok": "LIFECYCLE_SHUTDOWN_OK" in stdout,
        "init_2_ok": "LIFECYCLE_INIT_2" in stdout,
        "reset_org_ok": "LIFECYCLE_RESET_ORG=" in stdout,
        "org_match": False,
        "gate_1_ok": False,
        "gate_2_ok": False,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("LIFECYCLE_ORG_MATCH="):
            f["org_match"] = line.split("=", 1)[1].strip().lower() == "true"
        elif line.startswith("LIFECYCLE_GATE_1_OK"):
            f["gate_1_ok"] = True
        elif line.startswith("LIFECYCLE_GATE_2_OK"):
            f["gate_2_ok"] = True
    # PASS conditions:
    # - init + shutdown + re-init all complete
    # - org_id is consistent across re-init
    if f["init_1_ok"] and f["shutdown_ok"] and f["init_2_ok"] and f["reset_org_ok"]:
        if f["org_match"]:
            f["verdict"] = "PASS"
        else:
            f["verdict"] = "REVIEW"
    else:
        f["verdict"] = "BLOCK"
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
    rc = run_tc(30, "lifecycle", runner_path=EXAMPLES / "_tc30_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
