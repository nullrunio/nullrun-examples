"""TC-8: chain heartbeat — verify /heartbeat accepts chain_id and returns 200."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout: str, dump_path):
    f = {
        "heartbeat_calls": stdout.count("HEARTBEAT["),
        "heartbeat_failures": stdout.count("HEARTBEAT[") - stdout.count("HEARTBEAT["),
        "heartbeat_status_200": False,
        "heartbeat_request_has_chain_id": False,
        "verdict": "ERROR",
    }
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/heartbeat" in url:
                    if c.get("response_status") == 200:
                        f["heartbeat_status_200"] = True
                    req = c.get("request") or {}
                    if req.get("chain_id"):
                        f["heartbeat_request_has_chain_id"] = True
        except Exception:
            pass
    if f["heartbeat_status_200"] and f["heartbeat_request_has_chain_id"]:
        f["verdict"] = "PASS"
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
    rc = run_tc(8, "heartbeat", runner_path=EXAMPLES / "_tc8_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
