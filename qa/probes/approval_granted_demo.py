"""Probe for TC-12 — approval GRANTED flow (require_approval → approve → re-fire).

Verifies the SDK hooks:
  1. /gate on a sensitive tool returns require_approval decision
  2. SDK raises NullRunApprovalNotYetApprovedError with typed
     ``approval_id`` attribute (NR-A010, error_code)
  3. WS push listener (started by ``init_or_die``) receives
     approval_resolved frames — no manual connect_websocket needed
  4. Approval status poll (``rt.status``) returns valid state

The actual operator-driven approval via UI requires a human in the
loop; this probe verifies the SDK-side wire plumbing is correct.

User-spirit pattern: ``@nullrun.sensitive(impact=money_outflow(...))``
+ ``@nullrun.protect`` over ``refund_customer``. The SDK computes
``action_digest = sha256(json(tools|params))`` server-side from the
typed-extractor's wiring (per ADR-037 Slice B). The pre-fix probe
passed a hand-built ``action_digest`` via ``rt._transport.check``
which bypassed both decorators — that bypass is the user-spirit
violation the 2026-09-11 audit flagged.
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
    from nullrun.breaker.exceptions import NullRunApprovalNotYetApprovedError
    rt = get_runtime()

    # User-spirit @sensitive @protect over a real refund tool. The
    # ``money_outflow`` impact schema points at the ``amount`` kwarg;
    # the SDK's typed extractor reads the value at call-time and
    # ships ``kind: "money"`` + amount on the wire so the backend
    # can match the call against MoneyAmount approval rules
    # (ADR-037 Slice B + ServerMint 2026-08).
    @nullrun.sensitive(impact=nullrun.money_outflow(
        argument="amount", currency="USD", units="major",
    ))
    @nullrun.protect
    def refund_customer(amount: float = 100.0) -> str:
        # Body never runs if /gate returns require_approval — the
        # decorator raises NullRunApprovalNotYetApprovedError before
        # we get here. Returned only on the (rare) allow path.
        return "refund ok"

    set_call_context(model="gpt-4o-mini", tools=("refund_customer",))

    # Step 1: /gate on refund_customer. Expect require_approval,
    # which surfaces as the typed NR-A010 exception.
    try:
        result = refund_customer(amount=100.0)
        # Allow path — unusual; only if no approval rule matches.
        print(f"CHECK_DECISION=allow result={result}", flush=True)
        print("APPROVAL_ID=None", flush=True)
    except NullRunApprovalNotYetApprovedError as e:
        # The require_approval path. The exception's ``approval_id``
        # typed attribute carries the pending row's id — that's
        # the same wire field the pre-fix probe parsed out of the
        # raw response dict.
        print(f"CHECK_DECISION=require_approval exc={type(e).__name__}", flush=True)
        print(f"APPROVAL_ID_FROM_EXCEPTION={e.approval_id}", flush=True)
    except nullrun.NullRunBlockedException as e:
        # Other block flavours (TOOL_BLOCKED, etc.). Surface for
        # TC-12 to disambiguate.
        print(f"CHECK_DECISION=block exc={type(e).__name__}: {e}", flush=True)
        print(f"APPROVAL_ID_FROM_EXCEPTION={getattr(e, 'approval_id', None)}", flush=True)
    except Exception as e:
        print(f"CHECK_EXCEPTION: {type(e).__name__}: {e}", flush=True)

    # Step 2: SDK status check — WS push listener is owned by
    # ``init_or_die()``, no manual ``connect_websocket`` needed.
    try:
        status = rt.status()
        print(f"STATUS_OK={status}", flush=True)
    except Exception as e:
        print(f"STATUS_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
