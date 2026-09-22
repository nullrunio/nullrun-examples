"""Phase 1 / MVP 1.1 -- ToolParameters Approval Rules demo.

Demonstrates the three ways to attach a typed impact to a tool now
that Phase 1 / MVP 1.1 (Tier 2 of Razryv 2) is live on the backend:

    1. ``@protect``                                -- default extractor.
       Auto-attaches ``ToolParamsExtractor(include_all=True)``;
       every kwarg lands on the wire under its own name.
    2. ``@protect @sensitive(impact=tool_params({...}))`` -- explicit
       map. Renames kwargs and/or picks which args land on the wire.
    3. ``@protect @sensitive(impact=money_outflow(...))``  -- Phase 1
       Money variant. Typed extractor that converts
       ``Decimal(units="major")`` to integer minor units and
       rejects ``float`` (no IEEE-754 precision loss).

All three ship the same wire shape (a ``BusinessImpact`` envelope
with a SHA-256 ``action_digest``); only the discriminator
(``kind: "money"`` vs ``kind: "tool_call"``) and the body differ.
The backend's ``approval_eval.rs::action_predicate_matches`` then
branches on the discriminator to route to the right matcher.

Setup on the dashboard before running:

    /control-center/policies/approval-rules
        -> New rule
        -> Workflow: <your API key's bound workflow>
        -> Tool patterns: *
        -> Typed condition: ToolParameters
        -> Condition:  param_name="delete_force"  matcher="equals"  value=true
        -> Action:     require_approval
        -> Priority:   100
        -> Timeout:    300

When the rule fires, every ``delete_user(force=True)`` call lands
on /control-center/approvals as a PENDING row. Calls with
``force=False`` (or any other ``force`` value) bypass the rule
entirely.

Then run:

    pip install nullrun
    export NULLRUN_API_KEY=nr_live_...
    python examples/tool_params_demo.py

The script calls the three variants of the tool in order so you can
see each one on the wire (via the dashboard audit log) and through
the approval rule (via the Approvals page).
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import json
from decimal import Decimal

import nullrun
from nullrun import shutdown
from nullrun.breaker.exceptions import NullRunBlockedException
from nullrun.decorators import protect, sensitive
from nullrun.extractor import money_outflow, tool_params

# 0.18.1: NO init_or_die() -- the first @protect call below
# lazily creates the runtime.


# ──────────────────────────────────────────────────────────────────────────────
# 1. Three variants of the same tool.
#
# They are three DECORATOR PATTERNS, not three tools. The body is
# identical -- the difference is purely which BusinessImpact
# variant lands on the wire. Operators write ONE ToolParameters
# rule on the dashboard and it matches all three (because the
# backend matcher branches on the discriminated kind field).
# ──────────────────────────────────────────────────────────────────────────────


# Variant 1: ``@protect`` -- auto-attached default.
#
# Use this when:
#   - The function has few, named args.
#   - The operator-facing rule name matches the function-arg name
#     (or the rule references the arg directly without renaming).
@protect
def delete_user_auto(user_id: str, force: bool) -> str:
    """``delete_user_auto`` -- @protect alone, auto-attached extractor.

    Wire payload (BusinessImpact.kind="tool_call"):
        tool_name="delete_user_auto"
        params={"user_id": ..., "force": ...}     # all kwargs
    """
    return json.dumps({"status": "ok", "tool": "delete_user_auto", "force": force})


# Variant 2: ``@sensitive(impact=tool_params({...}))`` -- explicit map.
#
# Use this when:
#   - The operator-facing rule name ("delete_force") diverges from
#     the function-arg name ("force"). The map decouples the rule
#     from the function signature so a Python refactor of
#     ``force`` -> ``force_destructive`` does NOT silently break
#     every ToolParameters rule.
#   - Only a subset of the function's kwargs are operator-visible.
#     Here we forward only ``force`` -- the SDK still masks
#     ``user_id`` away for PII; the wire payload is just
#     ``{delete_force: true}``.
@sensitive(impact=tool_params({"delete_force": "force"}))
@protect
def delete_user_explicit(force: bool, user_id: str) -> str:
    """``delete_user_explicit`` -- tool_params with explicit rename map.

    Wire payload (BusinessImpact.kind="tool_call"):
        tool_name="delete_user_explicit"
        params={"delete_force": <force value>}
    """
    return json.dumps({"status": "ok", "tool": "delete_user_explicit", "force": force})


# Variant 3: ``@sensitive(impact=money_outflow(...))`` -- Phase 1 Money.
#
# Use this when:
#   - The rule is about money, not arbitrary tool args.
#   - You want a typed money extractor that converts
#     ``Decimal(units="major")`` to integer minor units and
#     rejects ``float`` (no IEEE-754 precision loss).
#   - You do NOT want the operator to see other kwargs like
#     ``customer_id`` -- the Money variant does not capture them.
@sensitive(impact=money_outflow(
    argument="refund_amount",
    currency="USD",
    units="major",
))
@protect
def refund_customer(refund_amount, customer_id: str) -> str:
    """``refund_customer`` -- money_outflow extractor.

    Wire payload (BusinessImpact.kind="money"):
        direction="outflow"
        amount_minor=<refund_amount * 100>
        currency="USD"
    """
    return json.dumps({
        "status": "ok",
        "tool": "refund_customer",
        "refund_amount": str(refund_amount),
        "customer_id": customer_id,
    })


# ──────────────────────────────────────────────────────────────────────────────
# 2. Main -- invoke all three so the operator can see each on the
# dashboard.
#
# With the ToolParameters rule from the module docstring
# (param_name="delete_force", matcher=equals, value=true), variant
# 2 -- delete_user_explicit(force=True) -- fires the rule because
# the rename map lands it on the wire as {delete_force: true}.
# Variant 1 -- delete_user_auto(force=True) -- does NOT match that
# rule because the auto-extracted param name is "force". Adjust
# the rule to ``force`` to also match variant 1.
# ──────────────────────────────────────────────────────────────────────────────
def _try_call(label: str, fn, **kwargs) -> None:
    """Invoke a @protect tool and print the result.

    Three possible outcomes (each printed with its source):
      * ``allow`` -- the gate returned allow and the body ran.
      * ``block`` -- the gate returned block (no approval needed
        for this rule; tool_block / rate_limit / budget cap etc.)
      * ``require_approval`` -- the operator must click Approve
        on the dashboard for the body to run. We do NOT block
        on the WS push in this demo because the test is
        fire-and-forget; instead we surface the exception so the
        operator can see the approval_id printed below.
    """
    print(f"\n[{label}] calling {fn.__name__}({sorted(kwargs)}) ...")
    try:
        result = fn(**kwargs)
        print(f"[{label}] decision=allow result={result[:120]}")
    except NullRunBlockedException as exc:
        # The gate fires `NullRunBlockedException` for blocks
        # AND for require_approval (the @protect wrapper turns
        # the WS-push timeout / Deny into the same exception
        # class so callers can `except` uniformly).
        print(f"[{label}] decision=block reason={exc.reason[:120]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[{label}] decision=error type={type(exc).__name__} exc={exc!r}")


if __name__ == "__main__":
    try:
        # Each call lives inside its own ``with nullrun.handle()``
        # so the WS-push approval flow has a clean cancellation
        # surface if the operator denies -- the script exits
        # cleanly on Deny rather than waiting out the full timeout.
        # In production code you would use ONE
        # ``with nullrun.handle()`` block around the whole agent
        # loop; this demo fires three independent calls so each
        # gets its own approval gate.
        with nullrun.handle():
            # (1) @protect alone -- auto-attached extractor
            # captures {"user_id": ..., "force": ...}. If the
            # rule param_name is "delete_force" (the renamed form
            # in variant 2), this call DOES NOT match the rule
            # because the wire payload uses "force" not
            # "delete_force". Edit the rule param_name to "force"
            # to also match this call.
            _try_call("auto", delete_user_auto,
                      user_id="cust-1", force=True)

        with nullrun.handle():
            # (2) Explicit rename: rule_param "delete_force" maps
            # to the function arg "force".
            _try_call("explicit-map", delete_user_explicit,
                      force=True, user_id="cust-1")

        with nullrun.handle():
            # (3) Money variant -- does not match the
            # ToolParameters rule. Matches a separate
            # ``when amount > $50 USD`` rule instead. Set up
            # that rule on the dashboard to see it fire.
            _try_call("money", refund_customer,
                      refund_amount=Decimal("75.00"), customer_id="cust-1")
    finally:
        shutdown()
