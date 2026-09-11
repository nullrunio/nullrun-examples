
import sys, threading
sys.path.insert(0, '.')
from examples._env import load_env
load_env()
from decimal import Decimal
import json, os, traceback
import nullrun
from nullrun import init_or_die, shutdown, chain
from nullrun.breaker.exceptions import NullRunBlockedException
from nullrun.decorators import protect, sensitive
from nullrun.extractor import money_outflow

# Background watchdog
_done = threading.Event()
def _watchdog():
    if not _done.wait(10.0):
        print('[probe-15] WATCHDOG_TIMEOUT 10s elapsed, hard-exiting', flush=True)
        os._exit(2)
threading.Thread(target=_watchdog, daemon=True).start()

init_or_die()
amount = Decimal('100.00')

@sensitive(impact=money_outflow(argument='refund_amount', currency='USD', units='major'))
@protect
def refund_customer(refund_amount, customer_id='cust-demo'):
    return json.dumps({'status':'ok'})

print('[probe-15] starting', flush=True)
try:
    with chain('ar-toolname-20260807-1', op='start'):
        try:
            with nullrun.handle():
                print('[probe-15] inside handle, calling refund', flush=True)
                result = refund_customer(refund_amount=amount)
                print(f'[probe-15] decision=allow result={result}', flush=True)
        except NullRunBlockedException as exc:
            print(f'[probe-15] decision=block reason={exc.reason!r} details={exc.details!r}', flush=True)
        except Exception as exc:
            print(f'[probe-15] decision=error type={type(exc).__name__} exc={exc!r}', flush=True)
            traceback.print_exc()
            print(flush=True)
except BaseException as exc:
    print(f'[probe-15] OUTER_EXCEPTION type={type(exc).__name__} exc={exc!r}', flush=True)
    traceback.print_exc()
    print(flush=True)
finally:
    _done.set()
    try:
        shutdown()
    except Exception as e:
        print(f'[probe-15] shutdown_error {e}', flush=True)
    print('[probe-15] done', flush=True)
