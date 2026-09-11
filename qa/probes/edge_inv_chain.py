"""EDGE-INV-CHAIN test: non-UUID chain_id should be rejected by SDK.

Drives runtime.check_workflow_budget() with various invalid chain_id formats
and captures the resulting errors.
"""
from __future__ import annotations

import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from examples._env import load_env  # type: ignore

load_env()

import nullrun
from nullrun import init_or_die, shutdown, get_runtime, set_call_context
from nullrun.breaker.exceptions import WorkflowKilledInterrupt, NullRunError

init_or_die()


def probe_with_chain(chain_id_value, label: str) -> dict:
    """Set chain context and call check_workflow_budget."""
    runtime = get_runtime()
    try:
        # Try with kwarg (newer API)
        try:
            set_call_context(chain_id=chain_id_value, chain_op="start")
        except TypeError:
            try:
                set_call_context(chain_id=chain_id_value)
            except Exception:
                pass
        except Exception:
            pass
    except Exception as e:
        return {"label": label, "set_err": type(e).__name__, "msg": str(e)[:120]}
    start = time.monotonic()
    try:
        result = runtime.check_workflow_budget()
        return {"label": label, "decision": "allow", "result": str(result)[:120], "elapsed": time.monotonic() - start}
    except WorkflowKilledInterrupt as exc:
        return {"label": label, "decision": "block", "code": getattr(exc, "code", None), "msg": str(exc)[:120], "elapsed": time.monotonic() - start}
    except Exception as e:
        return {"label": label, "decision": "error", "type": type(e).__name__, "msg": str(e)[:120], "elapsed": time.monotonic() - start}


def main():
    invalid_ids = [
        ("non_uuid_string", "not-a-uuid-at-all"),
        ("numeric_string", "12345"),
        ("special_chars", "!@#$%^&*()"),
        ("partial_uuid", "12345678-1234"),
        ("empty_string", ""),
        ("valid_uuid_zeros", "00000000-0000-0000-0000-000000000000"),
        ("valid_uuid_max", "ffffffff-ffff-ffff-ffff-ffffffffffff"),
    ]
    for label, cid in invalid_ids:
        try:
            r = probe_with_chain(cid, label)
            print(f"  [{label}] {cid!r:50s} -> {r}")
        except Exception as outer_e:
            print(f"  [{label}] {cid!r:50s} -> OUTER EXC {type(outer_e).__name__}: {outer_e}")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutdown()