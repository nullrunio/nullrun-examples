"""Approval Rule threshold probe (TOOLS-ABOVE 1/2/3).

TOOLS-ABOVE matcher fires when the action's ``money_outflow.amount``
crosses a configured threshold with a specific comparator:

    operator          condition                       example
    ──────────────    ──────────────────────────      ─────────────
    exceeds           amount >  threshold             amount=100.01 > 100
    equals or exceeds amount >= threshold             amount=99.00 >= 99
    equals            amount == threshold             amount=77.00 == 77

The operator-facing rule is configured separately on the dashboard
(Sidebar → Approval Rules → New rule → Typed condition: Money amount →
"When amount ..."). Each invocation of this script triggers ONE
``refund_customer`` call and waits for the operator's Approve / Deny
via the WebSocket push (mirrors ``ar_toolname_run.py`` exactly — only
the docstring differs because the rule-shape under test is
threshold-based, not TOOLNAME/ANY).

Three canonical scenarios (run by a shell wrapper, NOT by the script):

    1. python ar_threshold_run.py 99.99
       rule "When amount exceeds $100"           → expect NO approval
    2. python ar_threshold_run.py 100.00
       rule "When amount equals or exceeds $99"  → expect APPROVAL
    3. python ar_threshold_run.py 77.00
       rule "When amount equals $77"             → expect APPROVAL

Usage:
    python ar_threshold_run.py [amount_usd]

Where amount_usd is a string like '99.99' (default 100.00).
"""
from __future__ import annotations

from decimal import Decimal

import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env

load_env()

import json

import nullrun
from nullrun import init_or_die, shutdown
from nullrun.breaker.exceptions import NullRunBlockedException
from nullrun.decorators import protect, sensitive
from nullrun.extractor import money_outflow

init_or_die()

amount_str = sys.argv[1] if len(sys.argv) > 1 else "100.00"
amount = Decimal(amount_str)


@sensitive(impact=money_outflow(
    argument="refund_amount",
    currency="USD",
    units="major",
))
@protect
def refund_customer(refund_amount, customer_id="cust-demo"):
    print(f"  [refund] customer_id={customer_id!r} amount={refund_amount} USD -> OK (body ran)", flush=True)
    return json.dumps({"status": "ok", "customer_id": customer_id, "amount": str(refund_amount)})


if __name__ == "__main__":
    print(f"[ar_threshold_run] starting, amount={amount}", flush=True)
    try:
        with nullrun.handle():
            try:
                result = refund_customer(refund_amount=amount)
                print(f"[ar_threshold_run] decision=allow result={result}", flush=True)
            except NullRunBlockedException as exc:
                print(f"[ar_threshold_run] decision=block reason={exc.reason!r} details={exc.details!r}", flush=True)
            except Exception as exc:
                print(f"[ar_threshold_run] decision=error type={type(exc).__name__} exc={exc!r}", flush=True)
    finally:
        shutdown()