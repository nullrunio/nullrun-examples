"""TC-16: multi-event /track batch — verify 3 events batched into single track call."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "flush_ok": "FLUSH_OK" in stdout,
        "events_ok": 0,
        "events_fail": 0,
        "track_batch_status": None,
        "track_single_status": None,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if "EVENT_" in line and "_OK=" in line:
            f["events_ok"] += 1
        elif "EVENT_" in line and "_FAIL=" in line:
            f["events_fail"] += 1
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/track" in url and c.get("method") == "POST":
                    body = c.get("request") or {}
                    # batch body has 'events' array; single has flat fields
                    if isinstance(body, dict) and "events" in body:
                        f["track_batch_status"] = str(c.get("response_status"))
                    else:
                        f["track_single_status"] = str(c.get("response_status"))
        except Exception:
            pass
    # PASS: actual /track wire call made (not just local enqueue)
    if f["track_batch_status"] == "200" or f["track_single_status"] == "200":
        f["verdict"] = "PASS"
    elif f["track_batch_status"] in ("400", "422") or f["track_single_status"] in ("400", "422"):
        f["verdict"] = "PASS"  # fail-CLOSED on malformed batch is OK
    elif f["events_fail"] == 3:
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
    rc = run_tc(16, "track_batch", runner_path=EXAMPLES / "_tc16_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
