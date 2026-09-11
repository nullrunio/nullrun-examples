"""TC-AR-010 verification — bypass pre-flight /gate and use runtime.execute directly.

The SDK's check_workflow_budget() sends to /gate without tools field unless
set_call_context is called. For sensitive tools, runtime.execute() goes
to /execute but only sends `tool` singular not `tools` array.

This probe uses runtime.execute() directly to test the approval rule
path, but with a workaround: we monkey-patch the transport.execute to
populate tools array.

TC-AR-010 expects: decision=require_approval + approval_id.
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import os, json
from decimal import Decimal

# Patch transport.execute BEFORE init_or_die
import nullrun.transport as nr_transport
import nullrun.runtime as nr_runtime
_orig_execute = nr_transport.Transport.execute

def patched_execute(self, *args, **kwargs):
    """Inject tools=[tool] so TB-1 doesn't fire."""
    if 'tool' in kwargs and 'tools' not in kwargs:
        kwargs['tools'] = [kwargs['tool']]
    print(f'[DEBUG exec_req patched] tools={kwargs.get("tools")}', flush=True)
    res = _orig_execute(self, *args, **kwargs)
    print(f'[DEBUG exec_resp] {json.dumps(res, default=str)[:2000]}', flush=True)
    return res
nr_transport.Transport.execute = patched_execute

import nullrun
from nullrun import init_or_die, shutdown, handle
from nullrun.breaker.exceptions import NullRunBlockedException
from nullrun.decorators import protect, sensitive
from nullrun.extractor import money_outflow

init_or_die()

amount = Decimal('100.00')

@sensitive(impact=money_outflow(
    argument='refund_amount',
    currency='USD',
    units='major',
))
@protect
def refund_customer(refund_amount, customer_id='cust-demo'):
    print(f'  [refund] body ran', flush=True)
    return json.dumps({'status': 'ok'})

try:
    with handle():
        try:
            result = refund_customer(refund_amount=amount)
            print(f'FINAL: decision=allow result={result}', flush=True)
        except NullRunBlockedException as exc:
            print(f'FINAL: decision=block reason={exc.reason!r}', flush=True)
        except Exception as exc:
            print(f'FINAL: decision=error type={type(exc).__name__} exc={exc!r}', flush=True)
finally:
    shutdown()