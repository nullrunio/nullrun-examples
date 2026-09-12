"""EDGE-PAR-CHAIN test: 5 parallel chain starts on same org via SDK.

Drives runtime.check_workflow_budget() in 5 parallel async tasks
with different chain_ids.

Each task stamps its own chain context via
``nullrun.context.set_chain_id`` / ``set_chain_op`` (context.py:190,
255) before the call. Pre-fix the probe tried
``set_call_context(chain_id=..., chain_op="start")`` — neither kwarg
exists in the real signature (only ``model=`` and ``tools=``, see
context.py:779-805). The TypeError was silently swallowed by the
nested try/except/pass arms, so the 5 parallel tasks ran without
chain context at all and the probe was testing 5 unrelated parallel
calls instead of 5 parallel chain starts.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from examples._env import load_env  # type: ignore

load_env()

import nullrun
from nullrun import init_or_die, shutdown, get_runtime
from nullrun.breaker.exceptions import WorkflowKilledInterrupt
from nullrun.context import set_chain_id, set_chain_op

init_or_die()


async def probe_async(chain_id: str) -> dict:
    """Async wrapper that sets a chain_id then calls check_workflow_budget."""
    runtime = get_runtime()
    set_chain_id(chain_id)
    set_chain_op("start")
    start = time.monotonic()
    try:
        result = runtime.check_workflow_budget()
        return {"chain_id": chain_id, "decision": "allow", "result": str(result)[:120], "elapsed": time.monotonic() - start}
    except WorkflowKilledInterrupt as exc:
        return {"chain_id": chain_id, "decision": "block", "code": getattr(exc, "code", None), "msg": str(exc)[:120], "elapsed": time.monotonic() - start}
    except Exception as e:
        return {"chain_id": chain_id, "decision": "error", "type": type(e).__name__, "msg": str(e)[:120], "elapsed": time.monotonic() - start}


async def main() -> None:
    chain_ids = [str(uuid.uuid4()) for _ in range(5)]
    start = time.monotonic()
    results = await asyncio.gather(*[probe_async(cid) for cid in chain_ids])
    elapsed = time.monotonic() - start
    print(f"Elapsed: {elapsed:.2f}s")
    for r in results:
        print(f"  chain {r['chain_id'][:8]} -> {r['decision']} ({r.get('code', '')}) msg={r.get('msg', '')[:80]}")
    print(f"\nDecisions: {sorted(set(r['decision'] for r in results))}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        shutdown()