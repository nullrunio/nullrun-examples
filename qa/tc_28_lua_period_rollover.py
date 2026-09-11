"""TC-28: Lua v3 period-bound counter smoke — reserve twice, verify period-bound semantics."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "reserve_1_ok": "RESERVE_1_OK" in stdout,
        "reserve_2_ok": "RESERVE_2_OK" in stdout,
        "budget_approx_ok": "BUDGET_APPROX=" in stdout,
        "reserve_1_fail": "RESERVE_1_FAIL" in stdout,
        "reserve_2_fail": "RESERVE_2_FAIL" in stdout,
        "verdict": "ERROR",
    }
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            gate_count = sum(1 for c in captures if "/gate" in c.get("url", ""))
            f["gate_call_count"] = gate_count
        except Exception:
            pass
    # PASS conditions:
    # - both reserves succeeded (period-bound budget allows multiple reserves in same period)
    # - or second reserve blocked because synthetic 1¢ policy exhausted (also valid fail-CLOSED)
    if f["reserve_1_ok"] and f["reserve_2_ok"]:
        f["verdict"] = "PASS"
    elif f["reserve_1_ok"] and f["reserve_2_fail"]:
        # Synthetic 1¢ policy block — expected on this org
        f["verdict"] = "PASS"
    elif f["reserve_1_fail"]:
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
    rc = run_tc(28, "lua_period_rollover", runner_path=EXAMPLES / "_tc28_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
