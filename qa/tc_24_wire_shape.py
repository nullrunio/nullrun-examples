"""TC-24: wire-shape edge cases — UTF-8, long names, regex meta, multi/empty tools."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "utf8_ok": "UTF8_OK" in stdout,
        "long_name_ok": "LONG_NAME_OK" in stdout,
        "regex_meta_ok": "REGEX_META_OK" in stdout,
        "multi_tools_ok": "MULTI_TOOLS_OK" in stdout,
        "empty_tools_ok": "EMPTY_TOOLS_OK" in stdout,
        "no_tools_ok": "NO_TOOLS_OK" in stdout,
        "all_passed": 0,
        "verdict": "ERROR",
    }
    checks = [
        f["utf8_ok"], f["long_name_ok"], f["regex_meta_ok"],
        f["multi_tools_ok"], f["empty_tools_ok"], f["no_tools_ok"],
    ]
    f["all_passed"] = sum(checks)
    # PASS if all 6 wire-shape variants return OK (or fail-CLOSED)
    if f["all_passed"] == 6:
        f["verdict"] = "PASS"
    elif f["all_passed"] >= 4:
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
    rc = run_tc(24, "wire_shape_edges", runner_path=EXAMPLES / "_tc24_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
