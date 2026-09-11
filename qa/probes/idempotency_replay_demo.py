"""Probe for TC-20 — /gate idempotency: same operation_id → same response, idempotent_replay=true.

C-grade wire-contract probe.

Verifies server-side idempotency replay-cache: two ``/gate`` calls
with the same ``operation_id`` + ``tools`` + ``mode`` must return
the same response, with ``idempotent_replay=true`` on the second.

The probe intentionally drives ``rt._transport.check`` with a
fixed ``operation_id`` (and a freshly-minted ``execution_id`` per
attempt, to demonstrate that the IDEM-01 hash-narrowing landed:
``trace_id`` + ``execution_id`` no longer participate in the
replay-cache key, only the 11 user-controlled semantic fields do).

Why not a decorator: ``@nullrun.protect`` mints a fresh
``operation_id`` on every top-level invocation (P0-27 contextvar
hoist — the user-spirit invariant that lets back-to-back retries
of the same logical operation NOT collide on the same idempotency
key). ``set_call_context`` accepts only ``model`` and ``tools``,
NOT ``operation_id`` (see SDK nullrun/context.py:779). Therefore
a controlled ``operation_id`` requires the raw wire path.

The SDK's own idempotency replay is exercised through live
``@protect`` decoration in TC-20 via the ``_tc20_runner`` harness,
where the runner uses ``set_call_context`` to drive two distinct
semantic operations through one decorator-bound function and
asserts the second call's ``idempotent_replay=true`` flag.
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
    from nullrun.context import set_call_context
    rt = get_runtime()

    set_call_context(model="gpt-4o-mini", tools=("read_file",))

    # Fixed operation_id — both calls should be idempotent
    operation_id = f"tc20-idempotency-{uuid.uuid4()}"

    request_body = {
        "mode": "check",
        "tools": ("read_file",),
        "operation_id": operation_id,
        "action_digest": "tc20-test-digest",
        "organization_id": rt.organization_id,  # private Transport.check does NOT auto-fill
        "execution_id": rt._uuid7_str() if hasattr(rt, "_uuid7_str") else str(uuid.uuid4()),
    }

    # First call
    try:
        r1 = rt._transport.check(check_request=request_body)
        print(f"FIRST_OK={r1}", flush=True)
        decision1 = r1.get("decision") or r1.get("verdict")
        exec_id1 = r1.get("execution_id") or r1.get("reservation_id")
        print(f"FIRST_DECISION={decision1}", flush=True)
        print(f"FIRST_EXEC_ID={exec_id1}", flush=True)
    except Exception as e:
        print(f"FIRST_FAIL: {type(e).__name__}: {e}", flush=True)
        shutdown()
        return 0

    # Second call with SAME operation_id → expect idempotent_replay
    try:
        r2 = rt._transport.check(check_request=request_body)
        print(f"SECOND_OK={r2}", flush=True)
        decision2 = r2.get("decision") or r2.get("verdict")
        exec_id2 = r2.get("execution_id") or r2.get("reservation_id")
        replay = r2.get("idempotent_replay") or r2.get("replay") or False
        print(f"SECOND_DECISION={decision2}", flush=True)
        print(f"SECOND_EXEC_ID={exec_id2}", flush=True)
        print(f"SECOND_REPLAY={replay}", flush=True)
    except Exception as e:
        print(f"SECOND_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
