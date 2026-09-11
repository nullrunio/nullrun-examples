"""TC-21: workflow state catalog — verify all 6 typed exceptions exposed."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    expected = [
        "NullRunWorkflowInactiveError",
        "NullRunWorkflowKilledError",
        "NullRunChainError",
        "WorkflowKilledException",
        "WorkflowKilledInterrupt",
        "WorkflowPausedException",
    ]
    f = {
        "classes_present": 0,
        "classes_missing": [],
        "verdict": "ERROR",
    }
    for cls in expected:
        if f"{cls}_EXISTS=True" in stdout:
            f["classes_present"] += 1
        else:
            f["classes_missing"].append(cls)
    if f["classes_present"] == len(expected):
        f["verdict"] = "PASS"
    elif f["classes_present"] >= len(expected) - 1:
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
    rc = run_tc(21, "workflow_state", runner_path=EXAMPLES / "_tc21_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
