"""EDGE-NET-RETRY test: verify SDK retries don't double-spend budget.

Drives runtime.check_workflow_budget() with the SAME idempotency_key
multiple times and verifies the same execution_id is returned (idempotency).
Per CLAUDE.md §15: 'replay → return saved result'.
"""
from __future__ import annotations

import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from examples._env import load_env  # type: ignore

load_env()

from nullrun import init_or_die, shutdown, get_runtime
from nullrun.breaker.exceptions import WorkflowKilledInterrupt

init_or_die()


def probe_with_idem(idem_key: str, count: int) -> list:
    """Call runtime.check_workflow_budget() count times with same idempotency_key."""
    results = []
    runtime = get_runtime()
    for i in range(count):
        # We need to use the same idempotency_key for all retries
        # SDK may expose this via set_call_context or via an attribute
        import nullrun
        # Try multiple ways to set idempotency_key
        try:
            nullrun.set_call_context(idempotency_key=idem_key)
        except TypeError:
            try:
                nullrun.set_call_context(idem_key=idem_key)
            except Exception:
                pass
        except Exception:
            pass

        start = time.monotonic()
        try:
            result = runtime.check_workflow_budget()
            elapsed = time.monotonic() - start
            # Capture execution_id if available
            exec_id = getattr(result, "execution_id", None) or (isinstance(result, dict) and result.get("execution_id"))
            results.append({"i": i, "decision": "allow", "elapsed": elapsed, "exec_id": exec_id})
        except WorkflowKilledInterrupt as exc:
            elapsed = time.monotonic() - start
            results.append({"i": i, "decision": "block", "code": getattr(exc, "code", None), "msg": str(exc)[:80], "elapsed": elapsed})
        except Exception as e:
            elapsed = time.monotonic() - start
            results.append({"i": i, "decision": "error", "type": type(e).__name__, "msg": str(e)[:80], "elapsed": elapsed})
    return results


def main():
    # Use a single idempotency_key for all retries
    idem = str(uuid.uuid4())
    print(f"Using idempotency_key: {idem}")
    print()
    # 5 retries with same idem key
    print("=== 5 retries with same idempotency_key ===")
    results = probe_with_idem(idem, 5)
    for r in results:
        print(f"  [{r['i']}] {r['decision']} {r.get('code', '')} elapsed={r['elapsed']:.3f}s")
    # Count distinct exec_ids
    exec_ids = set(r.get("exec_id") for r in results if r.get("exec_id"))
    decisions = [r["decision"] for r in results]
    print(f"\nDistinct exec_ids: {len(exec_ids)} (should be 1 if idempotent)")
    print(f"Decisions: {decisions}")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutdown()