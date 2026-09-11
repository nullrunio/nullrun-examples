"""Probe for TC-15 — consume > reserve + ε → CONSUME_OVERBUDGET 422.

Strategy: reserve small (per-``@protect`` default) then consume
large via ``track_llm`` which sends real ``input_tokens``/
``output_tokens`` to ``/track``. ADR-005 fixed-ε default = 1¢;
the backend computes ``cost_cents`` from token counts via the
org's pricing policy. A 1M-token gpt-4o-mini call will exceed any
reasonable reserve by orders of magnitude.

User-spirit pattern: ``@nullrun.protect`` handles /gate (which
also does the Lua RESERVE) and the SDK's ``track_llm`` handles
the /track consume. The SDK propagates the active span from
``@protect`` to ``track_llm`` so the consume binds to the same
reservation. No manual ``_transport.check`` / ``_transport.track_single``
bypass.
"""
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

if len(sys.argv) >= 2:
    os.environ["NULLRUN_API_KEY"] = sys.argv[1]

import nullrun  # noqa: E402
from nullrun import init_or_die, shutdown  # noqa: E402
from nullrun.context import set_call_context  # noqa: E402

init_or_die()


def main() -> int:
    from nullrun import get_runtime
    rt = get_runtime()

    @nullrun.protect
    def probe() -> str:
        # Body returns the active span's reservation_id for the
        # stdout summary; the gate runs *before* we get here, so
        # the reserve has already happened via the decorator.
        return "ok"

    set_call_context(model="gpt-4o-mini", tools=("read_file",))

    # Step 1: /gate to reserve (decorator). SDK mints operation_id +
    # execution_id and binds the active span to this call.
    try:
        probe()
        print("GATE_OK", flush=True)
    except nullrun.NullRunBlockedException as e:
        # If the org's tool-block / approval policy blocks /gate,
        # we surface that as the gate failure (mirroring the prior
        # GATE_FAIL branch). TC-15 expects GATE_OK on a permissive
        # workflow.
        print(f"GATE_FAIL: {type(e).__name__}: {e}", flush=True)
        shutdown()
        return 0
    except Exception as e:
        print(f"GATE_FAIL: {type(e).__name__}: {e}", flush=True)
        shutdown()
        return 0

    # Step 2: /track via track_llm with token count that maps to a
    # cost far exceeding the reserve + ε. Backend computes
    # cost_cents from input_tokens + per-model pricing; a 1M-token
    # gpt-4o-mini call is ~$0.15 vs a typical 1¢ reserve.
    try:
        result = rt.track_llm(
            input_tokens=1_000_000,
            output_tokens=0,
            model="gpt-4o-mini",
        )
        print(f"TRACK_OK={result}", flush=True)
    except nullrun.NullRunConsumeOverbudgetError as e:
        # Expected: typed exception with CONSUME_OVERBUDGET wire code.
        print(f"TRACK_FAIL_OVERBUDGET: {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"TRACK_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
