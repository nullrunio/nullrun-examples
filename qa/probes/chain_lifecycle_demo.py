"""Probe for TC-6 — direct chain lifecycle exercise (no LLM dependency).

Exercises chain_start → chain_end through the runtime. The wire
tracer captures the full request/response bodies for both calls.

Run via TC-6 driver. Standalone (no driver)::

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \\
        qa/probes/chain_lifecycle_demo.py <api_key>
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

if len(sys.argv) >= 2 and not os.environ.get("NULLRUN_API_KEY"):
    os.environ["NULLRUN_API_KEY"] = sys.argv[1]

from nullrun import chain, init_or_die, shutdown  # noqa: E402

init_or_die()


def main() -> int:
    chain_id = str(uuid.uuid4())
    print(f"chain_id={chain_id}")

    # Open a chain via the contextmanager. The start /gate call goes
    # out with chain_id + chain_op=start. No LLM call happens here.
    with chain(chain_id, op="start"):
        print(f"chain[{chain_id}]: opened")

    # Explicitly close the chain. This calls Transport.chain_end which
    # (post-DEF-CHAIN-END-ORG-ID fix) sends the full GateRequest body.
    # The chain context manager auto-closes via the same transport
    # call, so this is a redundant-but-explicit second call that
    # proves the wire shape twice (idempotent 200 per backend docs).
    from nullrun import get_runtime
    rt = get_runtime()
    try:
        result = rt.chain_end(chain_id)
        print(f"chain_end explicit: {result}")
    except Exception as e:
        print(f"chain_end explicit: {type(e).__name__}: {e}")

    print("CHAIN_LIFECYCLE_COMPLETE")
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
