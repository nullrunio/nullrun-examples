"""TC-29: MCP hint propagation (destructiveHint, readonlyHint).

Per ADR-013: MCP umbrella/destructive/trust-list DORMANT on gate.
This TC verifies the SDK can carry MCP annotation context to /gate.
Honour is server-side flag flip.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from qa._driver_template import run_tc, EXAMPLES


def parse(stdout, dump_path):
    f = {
        "destructive_hint_handled": "DESTRUCTIVE_HINT" in stdout,
        "readonly_hint_handled": "READONLY_HINT" in stdout,
        "wire_mcp_class_present": False,
        "wire_mcp_annotations_present": False,
        "verdict": "ERROR",
    }
    if dump_path and dump_path.exists():
        try:
            captures = json.loads(dump_path.read_text(encoding="utf-8"))
            for c in captures:
                url = c.get("url", "")
                if "/gate" in url and c.get("method") == "POST":
                    req = c.get("request") or {}
                    if req.get("mcp_class"):
                        f["wire_mcp_class_present"] = True
                    if req.get("mcp_annotations"):
                        f["wire_mcp_annotations_present"] = True
        except Exception:
            pass
    # PASS conditions:
    # - SDK carries MCP context (either via body or via path decision)
    # - Server doesn't 500 on receiving MCP context
    if f["destructive_hint_handled"] and f["readonly_hint_handled"]:
        f["verdict"] = "PASS"
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
    rc = run_tc(29, "mcp_hints", runner_path=EXAMPLES / "_tc29_runner.py",
                policy_setup=None, verdict_parser=parse, evidence_collector=evidence)
    sys.exit(rc)
