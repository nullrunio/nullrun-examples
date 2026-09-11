"""Debug script: print actual /gate request body."""
import sys
import json
import httpx

# Patch httpx.Client.send to log request body
_orig_send = httpx.Client.send


def _send_patched(self, request, *args, **kw):
    if '/api/v1/gate' in str(request.url) and request.content:
        print('=== ACTUAL HTTP REQUEST BODY ===', flush=True)
        try:
            print(json.dumps(json.loads(request.content), indent=2, default=str), flush=True)
        except Exception:
            print(request.content.decode('utf-8', errors='replace'), flush=True)
        print('================================', flush=True)
    return _orig_send(self, request, *args, **kw)


httpx.Client.send = _send_patched

# Patch check_workflow_budget to log the computed digest
from nullrun.business_impact import (
    BusinessImpact as _BusinessImpact,
    compute_action_digest as _compute_action_digest,
)
import nullrun.runtime as _r
_orig_check = _r.NullRunRuntime.check_workflow_budget


def _check_patched(self, *args, **kwargs):
    digest = _compute_action_digest(_BusinessImpact.no_impact())
    print('LOCAL DIGEST VALUE: ' + repr(digest), flush=True)
    print('LOCAL DIGEST HEX64: ' + digest, flush=True)
    return _orig_check(self, *args, **kwargs)


_r.NullRunRuntime.check_workflow_budget = _check_patched

from _env import load_env

load_env()
import nullrun
from openai import OpenAI
from nullrun import guarded, protect, shutdown

nullrun.init_or_die()


@guarded
@protect
def answer(prompt):
    client = OpenAI()
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': prompt}],
    )
    return response.choices[0].message.content or ''


try:
    print('CALLING answer()...', flush=True)
    print('id(_BusinessImpact) before call:', id(_BusinessImpact), flush=True)
    print('_BusinessImpact.__dict__ keys:', list(_BusinessImpact.__dict__.keys()), flush=True)
    print('Has no_impact:', hasattr(_BusinessImpact, 'no_impact'), flush=True)
    result = answer('What is 2+2?')
    print('--- ANSWER: ' + str(result), flush=True)
except Exception as e:
    import traceback
    traceback.print_exc()
    print('EXCEPTION: ' + type(e).__name__ + ': ' + str(e), flush=True)
finally:
    shutdown()
