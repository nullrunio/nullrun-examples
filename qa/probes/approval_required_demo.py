"""Tier-1 demo probe: sensitive tool requiring operator approval (NR-A010..A015).

Drives a ``@sensitive`` / ``@protect`` flow whose policy enforces
``require_approval`` (Hard-always). The first /check returns
``decision=require_approval`` and the SDK raises
``NullRunApprovalNotYetApprovedError`` (NR-A010) until an operator
decides the pending grant in the dashboard. This probe verifies:

  1. The SDK raises the typed NR-A010 exception (not the generic
     NR-X001 fallback).
  2. The exception carries ``approval_id`` so the host code can
     show the operator a meaningful "wait, request <id> is pending"
     message — cookbook recipe pattern.

Out-of-scope for this probe: the operator-decision half (NR-A011 /
NR-A012 / NR-A013 / NR-A014 / NR-A015). Those require a separate
session driving the dashboard / WebSocket push to resolve the
pending grant, and are covered by the langgraph_openai_approval_demo
probes + the family-B wire probes under
``explotarory testing/qa/probes``.

Usage:
    python qa/probes/approval_required_demo.py

Pre-req:
    - Workflow with at least one policy whose ``enforcement_mode``
      is Hard and ``require_approval=true`` (e.g. ``refund_customer``
      under a ``TOOLS-ANY / tool_pattern=refund_customer`` policy).
    - NULLRUN_API_KEY / NULLRUN_API_URL in .env
"""
from __future__ import annotations
import os, sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

# Force a short approval-wait timeout so the SDK doesn't block on
# the default 300s wait when the operator never decides the pending
# grant (verified 2026-09-11 against runtime.py:_wait_for_approval_resolution).
# The /gate response carries `approval_timeout_seconds` from the server,
# but we clamp via this env var as the lower bound on the wait — the
# probe's goal is to verify the typed exception, not to actually wait
# for an operator decision.
os.environ.setdefault("NULLRUN_APPROVAL_TIMEOUT_SECONDS", "5")

import json
from decimal import Decimal

import nullrun
from nullrun import init_or_die, shutdown, set_call_context
from nullrun.breaker.exceptions import (
    NullRunApprovalNotYetApprovedError,
    NullRunApprovalDeniedError,
    NullRunApprovalExpiredError,
    NullRunApprovalDigestMismatchError,
    NullRunApprovalReplayRejectedError,
    NullRunBlockedException,
)
from nullrun.decorators import protect, sensitive
from nullrun.extractor import money_outflow

init_or_die()


@sensitive(impact=money_outflow(
    argument="refund_amount",
    currency="USD",
    units="major",
))
@protect
def refund_customer(refund_amount, customer_id="cust-demo"):
    """Sensitive: any money-outflow action requires operator approval.

    Mirrors the pattern used by ``refund_customer`` in the cookbook;
    the policy under test is the workflow-level approval rule with
    ``tool_pattern=refund_customer`` + ``require_approval=true``.
    """
    return json.dumps({
        "status": "ok",
        "customer_id": customer_id,
        "amount": str(refund_amount),
    })


print(f"[APPROVAL-DEMO] driving refund_customer(...) via direct call", flush=True)

# Set tools context to ensure /gate's tool_block rule (which has
# reason="no_tools_field" as a default-block in this org) does not
# pre-empt the approval test. The approval rule's tool_patterns
# = ["refund_customer"] matches by function name on the host
# side; we mirror the same name here so the orchestrator's
# pattern matcher sees the live tools list.
set_call_context(tools=["refund_customer"])

verdict = "PASS"
try:
    # Note: do NOT wrap with `with handle():` here. The handle()
    # wrapper catches any NullRunError (including the typed
    # approval exceptions we want to verify) and converts it to
    # `print(format_user_message(...)) + sys.exit(1)`, which
    # masks the typed subclass. The probe's except chain below
    # MUST see the exception to confirm wire code NR-A010/A011/
    # A012/etc. Matchable by cookbook handlers.
    result = refund_customer(refund_amount=Decimal("100.00"))
    # Pre-fix: refund_customer body would never run while pending
    # because the SDK raises before invoking the wrapped fn.
    # If we get here without raising, the policy isn't actually
    # enforcing approval — verdict REVIEW.
    print(f"[APPROVAL-DEMO] UNEXPECTED_ALLOW result={result}", flush=True)
    verdict = "REVIEW (policy did not require approval — check workflow config)"
except NullRunApprovalNotYetApprovedError as exc:
    # NR-A010: pending. Cookbook contract: this is NOT terminal.
    # The host code should block (WS push, polling, or wait for
    # operator response) — not raise. We raise here because the
    # probe runs without a registered waiter, so the SDK surfaces
    # the wait state as an exception the operator can see in logs.
    print(
        f"[APPROVAL-DEMO] NR-A010 (PENDING) "
        f"approval_id={exc.approval_id!r} "
        f"workflow_id={exc.workflow_id!r} "
        f"reason={exc.reason!r}",
        flush=True,
    )
    # Typed-class assertions (the bug NR-A010-2026-09-08 closed was
    # the SDK returning NullRunBlockedException + error_code="NR-A010"
    # instead of the typed NullRunApprovalNotYetApprovedError, which
    # broke cookbook ``except NullRunApprovalNotYetApprovedError:``).
    assert exc.error_code == "NR-A010", (
        f"approval-pending code must be NR-A010, got {exc.error_code!r}"
    )
    assert exc.approval_id, "approval_id must be populated for cookbook handlers"
    verdict = "PASS (NR-A010 typed + approval_id present)"
except NullRunApprovalDeniedError as exc:
    # NR-A011: operator denied. Terminal — same approval_id will
    # never succeed. Cookbook handlers must surface this to the
    # user as "request was not approved" (no retry on same id).
    print(f"[APPROVAL-DEMO] NR-A011 (DENIED) {exc!r}", flush=True)
    verdict = "PASS (NR-A011 typed — operator denied)"
except NullRunApprovalExpiredError as exc:
    # NR-A012: grant expired. See CLEANUP-A012-2026-09-08.
    print(f"[APPROVAL-DEMO] NR-A012 (EXPIRED) {exc!r}", flush=True)
    verdict = "PASS (NR-A012 typed)"
except NullRunApprovalDigestMismatchError as exc:
    # NR-A013: business-impact digest mismatch. Re-request needed.
    print(f"[APPROVAL-DEMO] NR-A013 (DIGEST-MISMATCH) {exc!r}", flush=True)
    verdict = "PASS (NR-A013 typed)"
except NullRunApprovalReplayRejectedError as exc:
    # NR-A015: approval already consumed.
    print(f"[APPROVAL-DEMO] NR-A015 (REPLAY) {exc!r}", flush=True)
    verdict = "PASS (NR-A015 typed)"
except NullRunBlockedException as exc:
    # Generic NullRunBlockedException fallback. Pre-fix the SDK
    # always raised this base class instead of the typed subclass;
    # cookbook ``except NullRunApprovalNotYetApprovedError:`` would
    # miss the typed code. Surface as REVIEW (regression class —
    # not the typed flow we want to verify).
    print(
        f"[APPROVAL-DEMO] generic NullRunBlockedException (NOT typed) "
        f"code={getattr(exc, 'error_code', None)} "
        f"reason={exc.reason!r}",
        flush=True,
    )
    verdict = (
        "REVIEW — SDK raised base NullRunBlockedException, not the "
        "typed NR-A010/NR-A011/NR-A012 subclass. Cookbook handlers "
        "branching on typed subclasses will miss this case."
    )
except Exception as exc:
    # Anything else: spec drift or transport outage.
    code = getattr(exc, "error_code", None)
    print(f"[APPROVAL-DEMO] UNEXPECTED type={type(exc).__name__} code={code} {exc!r}", flush=True)
    verdict = f"REVIEW — unexpected exception type {type(exc).__name__}"
finally:
    set_call_context(tools=[])
    shutdown()

print(f"[APPROVAL-DEMO] VERDICT={verdict}", flush=True)
