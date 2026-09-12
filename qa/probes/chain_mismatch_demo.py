"""Probe for TC-22 — chain org mismatch (CHAIN_ORG_MISMATCH) or max duration.

C-grade wire-contract probe.

Verifies the server-side anti-spoofing invariant: a ``/gate`` call
whose body claims a different ``organization_id`` than the
HMAC-signed runtime org must be rejected with ``CHAIN_ORG_MISMATCH``.

The probe intentionally drives ``rt._transport.check`` with a
spoofer ``organization_id`` (``\"00000000-...\"``) on the wire body
while the runtime's HMAC is signed with the real org id. The server
compares the two and rejects.

Why not a decorator: ``@nullrun.protect`` auto-fills the real
``organization_id`` on the wire body via the SDK transport
(``runtime.check_workflow_budget`` builds the request from the
runtime singleton). The decorator cannot ship a spoofed
``organization_id`` because that would defeat its own HMAC
contract — and rightly so.

The legitimate user-spirit pattern (Runtime A opens chain, Runtime
B tries to continue it via ``@protect``) requires runtime singleton
swapping mid-test, which the SDK does not expose. A future
\"multi-runtime @protect\" helper could close this gap; for now
the wire-level invariant is the only way to verify server-side
CHAIN_ORG_MISMATCH detection.

The SDK's own chain-mismatch path is exercised through live
``@protect`` decoration in TC-22 via the ``_tc22_runner`` harness
when the test workflow is set up to bind Runtime B to org A's chain.
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
    from nullrun import chain, get_runtime
    from nullrun.context import set_call_context
    rt = get_runtime()

    set_call_context(model="gpt-4o-mini", tools=("read_file",))

    chain_id = str(uuid.uuid4())
    print(f"chain_id={chain_id}", flush=True)

    # Open chain via /gate (in this org)
    try:
        with chain(chain_id, op="start"):
            print("CHAIN_STARTED", flush=True)

            # Try to use chain from a DIFFERENT org (cross-org attack)
            fake_org_id = "00000000-0000-0000-0000-000000000000"
            try:
                # Send a /gate with cross-org chain_id — server should reject.
                # NOTE: `Transport.check` returns a dict (NOT raises) for 4xx —
                # the `decision_source == GATEWAY` + `decision == "block"`
                # pair carries the wire-coded reason so the runtime can
                # dispatch via `NullRunBudgetError` / `NullRunChainError`.
                # Pre-fix the probe only inspected exceptions and printed
                # `CROSS_ORG_GATE_OK (unexpected!)` for the server's 403.
                check_resp = rt._transport.check(check_request={
                    "mode": "check",
                    "tools": ("read_file",),
                    "organization_id": fake_org_id,  # different org
                    "execution_id": str(uuid.uuid4()),
                    "chain_id": chain_id,
                    "chain_op": "continue",
                    "action_digest": "tc22-chain-mismatch",
                })
                decision = check_resp.get("decision")
                error_code = (
                    check_resp.get("error_code")
                    or check_resp.get("details", {}).get("error_code")
                )
                status_code = check_resp.get("status_code")
                if decision == "block" and error_code in {"ORG_MISMATCH", "CHAIN_ORG_MISMATCH"}:
                    print(
                        f"CROSS_ORG_GATE_BLOCKED: error_code={error_code} "
                        f"status_code={status_code} (expected)",
                        flush=True,
                    )
                else:
                    print(
                        f"CROSS_ORG_GATE_OK (unexpected!): decision={decision} "
                        f"error_code={error_code} status_code={status_code}",
                        flush=True,
                    )
            except Exception as e:
                print(f"CROSS_ORG_GATE_FAIL: {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"CHAIN_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
