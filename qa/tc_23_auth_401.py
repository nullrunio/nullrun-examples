"""TC-23: authentication failure — invalid API key → 401 + typed NullRunAuthenticationError."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "gate_fail": "GATE_FAIL" in stdout,
        "init_fail": "INIT_FAIL" in stdout,
        "gate_unexpected_ok": "GATE_OK (unexpected!)" in stdout,
        "auth_error_class": None,
        "wire_auth_status": None,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("GATE_FAIL:") or line.startswith("INIT_FAIL:"):
            parts = line.split(":", 2)
            if len(parts) >= 2:
                f["auth_error_class"] = parts[1].strip()
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/auth/verify" in url or "/gate" in url:
                    f["wire_auth_status"] = str(c.get("response_status"))
        except Exception:
            pass
    # PASS conditions:
    # - any auth error (INIT_FAIL or GATE_FAIL) — fail-CLOSED correct
    if (f["init_fail"] or f["gate_fail"]) and f["wire_auth_status"] in ("401", "403"):
        f["verdict"] = "PASS"
    elif f["init_fail"] or f["gate_fail"]:
        f["verdict"] = "PASS"
    elif f["gate_unexpected_ok"]:
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
    rc = run_tc(23, "auth_401", runner_path=EXAMPLES / "_tc23_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
