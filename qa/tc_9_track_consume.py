"""TC-9: real /track consume flow (reserve → consume)."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "reserve_ok": "RESERVE_OK" in stdout,
        "reserve_fail": "RESERVE_FAIL" in stdout,
        "track_ok": "TRACK_RESULT=" in stdout,
        "track_fail": "TRACK_FAIL" in stdout,
        "track_status": None,
        "gate_status": None,
        "verdict": "ERROR",
    }
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if url.endswith("/api/v1/gate"):
                    f["gate_status"] = str(c.get("response_status"))
                elif url.endswith("/api/v1/track"):
                    f["track_status"] = str(c.get("response_status"))
        except Exception:
            pass
    if f["reserve_ok"] and f["track_ok"]:
        f["verdict"] = "PASS"
    elif f["reserve_fail"] or f["track_fail"]:
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
    rc = run_tc(9, "track_consume", runner_path=EXAMPLES / "_tc9_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
