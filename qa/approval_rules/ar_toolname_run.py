"""Minimal SDK script for Approval Rule testing.

Calls the @protect-wrapped `refund_customer` tool ONCE with a fixed amount.
This triggers the approval rule (TOOLNAME/Any matching call). The SDK
blocks via WS push waiting for the operator to approve/deny via the UI.

Usage:
    python ar_toolname_run.py [amount_usd]

Where amount_usd is a string like '100.00' (default 100.00).
"""
from __future__ import annotations

from decimal import Decimal

import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env

load_env()

import json
import sys

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
    print(f"[ar_toolname_run] starting, amount={amount}", flush=True)
    try:
        with nullrun.handle():
            try:
                result = refund_customer(refund_amount=amount)
                print(f"[ar_toolname_run] decision=allow result={result}", flush=True)
            except NullRunBlockedException as exc:
                print(f"[ar_toolname_run] decision=block reason={exc.reason!r} details={exc.details!r}", flush=True)
            except Exception as exc:
                print(f"[ar_toolname_run] decision=error type={type(exc).__name__} exc={exc!r}", flush=True)
    finally:
        shutdown()