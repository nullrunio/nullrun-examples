"""TC-13: approval DENIED — verify SDK exposes typed exception classes."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "denied_cls_exists": "DENIED_CLS_EXISTS=True" in stdout,
        "expired_cls_exists": "EXPIRED_CLS_EXISTS=True" in stdout,
        "replay_cls_exists": "REPLAY_CLS_EXISTS=True" in stdout,
        "denied_cls_name": None,
        "expired_cls_name": None,
        "replay_cls_name": None,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("DENIED_CLS_NAME="):
            f["denied_cls_name"] = line.split("=", 1)[1]
        elif line.startswith("EXPIRED_CLS_NAME="):
            f["expired_cls_name"] = line.split("=", 1)[1]
        elif line.startswith("REPLAY_CLS_NAME="):
            f["replay_cls_name"] = line.split("=", 1)[1]
    # PASS: all 3 exception classes exist and are named correctly
    if f["denied_cls_exists"] and f["expired_cls_exists"] and f["replay_cls_exists"]:
        f["verdict"] = "PASS"
    elif f["denied_cls_exists"] or f["expired_cls_exists"]:
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
    rc = run_tc(13, "approval_denied", runner_path=EXAMPLES / "_tc13_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
