"""Probe for TC-16 — multi-event /track batch + partial-failure handling."""
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
    from nullrun.context import set_call_context
    rt = get_runtime()

    set_call_context(model="gpt-4o-mini", tools=("read_file", "write_file", "delete_file"))

    # Step 1: /gate via check_workflow_budget to mint execution_id
    try:
        rt.check_workflow_budget()
        print("GATE_OK", flush=True)
    except Exception as e:
        print(f"GATE_FAIL: {type(e).__name__}: {e}", flush=True)

    # Flush any in-flight events first
    try:
        rt._transport.flush_now()
    except Exception:
        pass

    # Enqueue 3 events via track_event
    results = []
    for i in range(3):
        try:
            r = rt.track_event(
                "llm_call",
                input_tokens=10 * (i + 1),
                output_tokens=5 * (i + 1),
                model="gpt-4o-mini",
                latency_ms=100,
            )
            results.append(("OK", i, str(r)[:80]))
        except Exception as e:
            results.append(("FAIL", i, f"{type(e).__name__}: {e}"))

    for status, idx, msg in results:
        print(f"EVENT_{idx}_{status}={msg}", flush=True)

    # Force flush
    try:
        rt._transport.flush_now()
        print("FLUSH_OK", flush=True)
    except Exception as e:
        print(f"FLUSH_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
