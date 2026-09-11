"""Probe for TC-26 — backend / transport error (5xx / network unreachable)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "examples"))
try:
    from _env import load_env
    load_env()
except Exception:
    pass

# Read the API key from the env (real one), then point to bad URL
api_key = os.environ.get("NULLRUN_API_KEY", "")
if not api_key or not api_key.startswith("nr_live_"):
    print("PROBE_SKIP: no valid NULLRUN_API_KEY in env", flush=True)
    sys.exit(0)

os.environ["NULLRUN_API_URL"] = "http://127.0.0.1:1"  # nothing listens here

from nullrun.runtime import NullRunRuntime  # noqa: E402
from nullrun.context import set_call_context  # noqa: E402


def main() -> int:
    try:
        NullRunRuntime.reset_instance()
    except Exception:
        pass
    try:
        rt = NullRunRuntime(
            api_key=api_key,
            api_url=os.environ["NULLRUN_API_URL"],
        )
        set_call_context(model="gpt-4o-mini", tools=("read_file",))

        try:
            rt.check_workflow_budget()
            print("GATE_OK (unexpected!)", flush=True)
        except Exception as e:
            print(f"GATE_FAIL: {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"INIT_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
