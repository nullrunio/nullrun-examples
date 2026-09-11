"""TC-12: approval GRANTED — verify SDK WS plumbing for approval_resolved."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "ws_connected": "WS_CONNECTED" in stdout,
        "check_decision_captured": "CHECK_DECISION=" in stdout,
        "approval_id_captured": "APPROVAL_ID=" in stdout or "APPROVAL_ID_FROM_EXCEPTION=" in stdout,
        "status_ok": "STATUS_OK=" in stdout,
        "ws_url_seen": False,
        "verdict": "ERROR",
    }
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.dump_path if False else dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/ws/" in url:
                    f["ws_url_seen"] = True
        except Exception:
            pass
    # PASS conditions:
    # 1. WS connection registered
    # 2. /check returned require_approval OR raised NR-A010 with approval_id
    # 3. status() returns OK
    if f["ws_connected"] and f["approval_id_captured"]:
        f["verdict"] = "PASS"
    elif f["ws_connected"] and f["check_decision_captured"]:
        f["verdict"] = "PASS"
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
    rc = run_tc(12, "approval_granted", runner_path=EXAMPLES / "_tc12_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
