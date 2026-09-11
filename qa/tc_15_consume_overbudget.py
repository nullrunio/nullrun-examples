"""TC-15: consume > reserve + ε → CONSUME_OVERBUDGET 422."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "gate_ok": "GATE_OK" in stdout,
        "track_fail": "TRACK_FAIL" in stdout,
        "track_ok": "TRACK_OK=" in stdout,
        "track_error_class": None,
        "track_status": None,
        "track_error_code": None,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("TRACK_FAIL:"):
            parts = line.split(":", 2)
            if len(parts) >= 2:
                f["track_error_class"] = parts[1].strip()
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/track" in url and c.get("method") == "POST":
                    f["track_status"] = str(c.get("response_status"))
                    resp = c.get("response") or {}
                    if isinstance(resp, dict):
                        f["track_error_code"] = resp.get("error_code") or (resp.get("details") or {}).get("error_code")
        except Exception:
            pass
    # PASS conditions:
    # 1. /track over-budget rejected with 422 CONSUME_OVERBUDGET
    # 2. SDK raises NullRunConsumeOverbudgetError (typed)
    if f["track_fail"] and f["track_error_class"] == "NullRunConsumeOverbudgetError":
        f["verdict"] = "PASS"
    elif f["track_status"] == "422" and f["track_error_code"] == "CONSUME_OVERBUDGET":
        f["verdict"] = "PASS"
    elif f["track_ok"] and f["track_status"] == "200":
        # Server accepted over-budget — silent fail-OPEN
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
    rc = run_tc(15, "consume_overbudget", runner_path=EXAMPLES / "_tc15_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
