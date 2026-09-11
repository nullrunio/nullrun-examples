"""TC-14: approval REPLAY — same approval_id → server returns idempotent response."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "check_ok": "CHECK_OK=" in stdout,
        "check_fail": "CHECK_FAIL" in stdout,
        "replay_ok": "REPLAY_OK=" in stdout,
        "replay_flag": None,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("REPLAY_FLAG="):
            f["replay_flag"] = line.split("=", 1)[1].lower() == "true"
    # PASS conditions:
    # 1. /check accepts approval_id field (wire-shape OK)
    # 2. Both calls complete (server doesn't crash on replay)
    if f["check_ok"] and f["replay_ok"]:
        if f["replay_flag"]:
            f["verdict"] = "PASS"  # full replay semantics
        else:
            f["verdict"] = "REVIEW"  # wire-shape OK but no replay flag
    elif f["check_fail"] or f["replay_ok"]:
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
    rc = run_tc(14, "approval_replay", runner_path=EXAMPLES / "_tc14_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
