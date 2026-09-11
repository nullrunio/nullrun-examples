"""Debug ar_toolname_run.py with patched transport to see request/response.

RUN 20260821-140626 — TC-SDK-014 verification.
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import os, json
from decimal import Decimal

# Patch transport BEFORE init_or_die
import nullrun.transport as nr_transport
_orig_check = nr_transport.Transport.check
_orig_execute = nr_transport.Transport.execute
def patched_check(self, request_body, *args, **kwargs):
    print(f'[DEBUG check_req] {json.dumps(request_body, default=str)}', flush=True)
    res = _orig_check(self, request_body, *args, **kwargs)
    print(f'[DEBUG check_resp] {json.dumps(res, default=str)}', flush=True)
    return res
def patched_execute(self, request_body, *args, **kwargs):
    print(f'[DEBUG exec_req] {json.dumps(request_body, default=str)[:1500]}', flush=True)
    res = _orig_execute(self, request_body, *args, **kwargs)
    print(f'[DEBUG exec_resp] {json.dumps(res, default=str)[:2000]}', flush=True)
    return res
nr_transport.Transport.check = patched_check
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