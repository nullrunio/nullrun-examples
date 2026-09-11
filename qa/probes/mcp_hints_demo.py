"""Probe for TC-29 — MCP hints propagation (destructiveHint, readonlyHint, etc.).

Per ADR-013: MCP umbrella/destructive/trust-list DORMANT on gate
(typed but not emitted). This probe verifies the SDK can carry MCP
annotation context to /gate; whether the gate honours them is a
server-side flag flip. Currently expected: hint fields ignored,
decision flows through tool_patterns.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "examples"))
try:
    from _env import load_env
    load_env()
except Exception:
    pass

if len(sys.argv) >= 2:
    os.environ["NULLRUN_API_KEY"] = sys.argv[1]

from nullrun import init_or_die, shutdown  # noqa: E402

init_or_die()


def main() -> int:
    from nullrun import get_runtime
    from nullrun.context import set_call_context, set_mcp_tool_context
    rt = get_runtime()

    # Test 1: destructiveHint=true with destructive tool
    set_call_context(model="gpt-4o-mini", tools=("delete_file",))
    set_mcp_tool_context(
        tool_class="destructive",
        annotations={"destructiveHint": True, "readonlyHint": False},
    )

    try:
        result = rt.check_workflow_budget()
        decision = "allow" if result is None else "check_returned"
        print(f"DESTRUCTIVE_HINT={decision}", flush=True)
    except Exception as e:
        print(f"DESTRUCTIVE_HINT: {type(e).__name__}: {e}", flush=True)

    # Test 2: readonlyHint=true with read tool (should always allow)
    set_call_context(model="gpt-4o-mini", tools=("read_file",))
    set_mcp_tool_context(
        tool_class="readonly",
        annotations={"destructiveHint": False, "readonlyHint": True},
    )
    try:
        result = rt.check_workflow_budget()
        print(f"READONLY_HINT=ok", flush=True)
    except Exception as e:
        print(f"READONLY_HINT: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
