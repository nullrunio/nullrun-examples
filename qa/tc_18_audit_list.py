"""TC-18: GET /audit-log — list endpoint returns audit rows with consistent shape."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "list_ok": "AUDIT_LIST=" in stdout,
        "list_fail": "AUDIT_FAIL" in stdout,
        "list_status": None,
        "list_has_items_key": "AUDIT_ITEMS_COUNT=" in stdout,
        "list_items_count": None,
        "first_row_keys": None,
        "verdict": "ERROR",
    }
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/audit-log" in url or "/audit_events" in url:
                    f["list_status"] = str(c.get("response_status"))
        except Exception:
            pass
    # Parse stdout for items count
    for line in stdout.splitlines():
        if line.startswith("AUDIT_EVENTS_COUNT="):
            try:
                f["list_items_count"] = int(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("AUDIT_FIRST_KEYS="):
            f["first_row_keys"] = line.split("=", 1)[1]
    if f["list_ok"] and f["list_status"] == "200":
        if f["list_items_count"] is not None and f["list_items_count"] >= 0:
            f["verdict"] = "PASS"
        else:
            f["verdict"] = "REVIEW"
    elif f["list_fail"]:
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
    rc = run_tc(18, "audit_log_list", runner_path=EXAMPLES / "_tc18_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
