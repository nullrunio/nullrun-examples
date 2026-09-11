"""Probe for TC-24 — wire-shape edge cases: UTF-8, long names, regex meta, multi-tools, empty tools."""
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
    rt = get_runtime()

    org_id = rt.organization_id

    def gate(tools, label, action_digest):
        try:
            r = rt._transport.check(check_request={
                "mode": "check",
                "tools": tools,
                "organization_id": org_id,
                "execution_id": str(uuid.uuid4()),
                "operation_id": f"tc24-{uuid.uuid4()}",
                "action_digest": action_digest,
                "estimated_tokens": 1,
            })
            print(f"{label}_OK decision={r.get('decision')}", flush=True)
            return True
        except Exception as e:
            print(f"{label}_FAIL: {type(e).__name__}: {e}", flush=True)
            return False

    # 1. UTF-8 tool_name (emoji + cyrillic)
    utf8_name = "🔧退款_кириллица"
    gate((utf8_name,), "UTF8", "tc24-utf8")

    # 2. Long tool name (>256 chars)
    long_name = "x" * 512
    gate((long_name,), "LONG_NAME", "tc24-long-name")

    # 3. Regex meta-chars in tool name (server should treat as literal)
    regex_name = "bash.*[abc]"
    gate((regex_name,), "REGEX_META", "tc24-regex-meta")

    # 4. Multi-tool: tools=["a", "b"]
    gate(("read_file", "write_file"), "MULTI_TOOLS", "tc24-multi-tools")

    # 5. Empty tools: []
    gate((), "EMPTY_TOOLS", "tc24-empty-tools")

    # 6. No tools field at all (omit)
    try:
        r = rt._transport.check(check_request={
            "mode": "check",
            "organization_id": org_id,
            "execution_id": str(uuid.uuid4()),
            "operation_id": f"tc24-{uuid.uuid4()}",
            "action_digest": "tc24-no-tools",
            "estimated_tokens": 1,
        })
        print(f"NO_TOOLS_OK decision={r.get('decision')}", flush=True)
    except Exception as e:
        print(f"NO_TOOLS_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
