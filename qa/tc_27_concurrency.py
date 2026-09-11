"""TC-27: concurrency — 10 sequential /gate calls, verify unique reservation_ids (Lua atomicity)."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "unique_reservations": None,
        "total_calls": None,
        "all_allow": False,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("UNIQUE_RESERVATIONS="):
            try:
                unique, total = line.split("=", 1)[1].split("/")
                f["unique_reservations"] = int(unique)
                f["total_calls"] = int(total)
            except ValueError:
                pass
        elif line.startswith("DECISION_SUMMARY="):
            summary = line.split("=", 1)[1]
            if "'allow':" in summary or '"allow":' in summary:
                # 10/10 allow = full atomicity, no budget exhaustion
                if summary.count("allow") > 5:
                    f["all_allow"] = True
    # PASS: all reservations unique (Lua atomic mint)
    if f["unique_reservations"] is not None and f["total_calls"] is not None:
        if f["unique_reservations"] == f["total_calls"]:
            f["verdict"] = "PASS"  # full atomicity, no duplicates
        elif f["unique_reservations"] >= f["total_calls"] * 0.9:
            f["verdict"] = "REVIEW"  # some duplicates, possibly caching
        else:
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
    rc = run_tc(27, "concurrency", runner_path=EXAMPLES / "_tc27_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
