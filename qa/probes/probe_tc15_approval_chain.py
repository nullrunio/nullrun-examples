"""TC-SDK-015 custom probe: approval rule inside chain() context with UUID v4 chain_id.

Wraps refund_customer @protect call inside a chain() context. Expects
the approval rule (TOOLS-ANY, tool_pattern=refund_customer) to trigger
pending approval. Verifies that approval behavior is preserved inside chain.
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import json, uuid
from decimal import Decimal
import nullrun
from nullrun import init_or_die, shutdown, chain
from nullrun.breaker.exceptions import NullRunBlockedException
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
    print(f"  [refund] customer_id={customer_id!r} amount={refund_amount} USD -> OK (body ran)", flush=True)
    return json.dumps({"status": "ok", "customer_id": customer_id, "amount": str(refund_amount)})

chain_id = str(uuid.uuid4())
print(f"[TC-SDK-015] chain_id={chain_id}", flush=True)
print(f"[TC-SDK-015] Starting chain + @protect call...", flush=True)

try:
    with chain(chain_id, op="start"):
        try:
            with nullrun.handle():
                result = refund_customer(refund_amount=Decimal("100.00"))
                print(f"[TC-SDK-015] decision=allow result={result}", flush=True)
        except NullRunBlockedException as exc:
            print(f"[TC-SDK-015] decision=block reason={exc.reason!r} details={exc.details!r}", flush=True)
        except Exception as exc:
            print(f"[TC-SDK-015] decision=error type={type(exc).__name__} exc={exc!r}", flush=True)
finally:
    shutdown()
