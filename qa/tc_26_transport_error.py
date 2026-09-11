"""TC-26: transport / backend error — unreachable host → typed exception (fail-CLOSED)."""
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
        "error_class": None,
        "verdict": "ERROR",
    }
    for line in stdout.splitlines():
        if line.startswith("GATE_FAIL:") or line.startswith("INIT_FAIL:"):
            parts = line.split(":", 2)
            if len(parts) >= 2:
                f["error_class"] = parts[1].strip()
    # PASS conditions:
    # - Transport failure raises typed exception (NullRunTransportError or similar)
    # - NOT silent fail-OPEN
    fail_closed_classes = {
        "NullRunTransportError",
        "NullRunBackendError",
        "NullRunInfrastructureError",
        "ConnectionError",
        "ConnectError",
        "httpx.ConnectError",
        "NullRunRateLimitRedisError",
    }
    if f["init_fail"] or f["gate_fail"]:
        if f["error_class"] in fail_closed_classes or "Error" in (f["error_class"] or ""):
            f["verdict"] = "PASS"
        else:
            f["verdict"] = "REVIEW"
    elif f["gate_unexpected_ok"]:
        f["verdict"] = "BLOCK"  # security: silent fail-OPEN
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
    rc = run_tc(26, "transport_error", runner_path=EXAMPLES / "_tc26_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
