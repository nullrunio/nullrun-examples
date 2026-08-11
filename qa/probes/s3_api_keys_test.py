"""Session 3 — API Keys smoke test using nullrun SDK.

Calls /api/v1/check via SDK check_workflow_budget for various scenarios:
  1. Valid key, no policy, allowed tool — allow
  2. Valid key, with tool name — exercises ToolBlock path
  3. Invalid key (revoked) — 401 / error
  4. Empty key — error
  5. Random garbage key — error
  6. nr_test_ prefix — different prefix handling

Output: prints log per scenario. Saves JSON to evidence/s3_api_keys.json.
"""
from __future__ import annotations
import os
import sys
import json
from datetime import datetime, timezone

from nullrun import init, get_runtime, set_call_context, shutdown
from nullrun.breaker.exceptions import WorkflowKilledInterrupt

RESULTS = []
API_KEY_VALID = os.environ.get("NULLRUN_API_KEY", "")


def log(scenario, status, detail=""):
    ts = datetime.now(timezone.utc).isoformat()
    line = {"ts": ts, "scenario": scenario, "status": status, "detail": detail}
    RESULTS.append(line)
    print(f"[{ts}] {scenario} -> {status} :: {detail}")


def probe_with_key(api_key, tool_name="bash"):
    """Init SDK with custom key, run probe, shutdown."""
    os.environ["NULLRUN_API_KEY"] = api_key
    try:
        init(api_key=api_key, api_url=os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io"))
    except SystemExit as e:
        log(f"init_key", "init_failed", f"key={api_key[:14]!r} code={e}")
        return
    except Exception as e:
        log(f"init_key", "init_exception", f"key={api_key[:14]!r} {type(e).__name__}: {e!r}")
        return

    set_call_context(tools=[tool_name])
    try:
        runtime = get_runtime()
        try:
            runtime.check_workflow_budget()
            log(f"probe", "allow", f"tool={tool_name} key={api_key[:14]!r}")
        except WorkflowKilledInterrupt as exc:
            log(f"probe", "block", f"tool={tool_name} key={api_key[:14]!r} {exc!r}")
        except Exception as e:
            log(f"probe", "exception",
                f"tool={tool_name} key={api_key[:14]!r} {type(e).__name__}: {e!r}")
    finally:
        set_call_context(tools=[])
        try:
            shutdown()
        except Exception:
            pass


def main():
    # S3.1 — valid key, allowed tool (no policy active)
    probe_with_key(API_KEY_VALID, tool_name="read_file")

    # S3.2 — valid key, bash (also no policy yet)
    probe_with_key(API_KEY_VALID, tool_name="bash")

    # S3.3 — valid key, MCP-style tool
    probe_with_key(API_KEY_VALID, tool_name="mcp://filesystem/delete_user")

    # S3.4 — invalid random key
    probe_with_key("nr_live_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", tool_name="bash")

    # S3.5 — empty key
    probe_with_key("", tool_name="bash")

    # S3.6 — garbage (wrong format)
    probe_with_key("not-an-api-key", tool_name="bash")

    # S3.7 — nr_test_ prefix
    probe_with_key("nr_test_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", tool_name="bash")

    # Evidence file: defaults to ./qa/logs/s3_api_keys.json so the script
    # is runnable from any checkout. Override with EVIDENCE_PATH to write
    # into a session-specific directory.
    import os, pathlib
    out_path = pathlib.Path(os.environ.get(
        "EVIDENCE_PATH",
        str(pathlib.Path(__file__).resolve().parents[1] / "logs" / "s3_api_keys.json"),
    ))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(RESULTS, f, indent=2)
    print(f"\n[evidence] wrote {len(RESULTS)} records to {out_path}")


if __name__ == "__main__":
    main()
