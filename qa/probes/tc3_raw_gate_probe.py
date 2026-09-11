"""TC-3 raw-gate probe: monkey-patch Transport.check to print the raw
response from /gate, then call check_workflow_budget() so we can see
exactly what decision + explanation the backend returned before the
SDK raises WorkflowKilledInterrupt.
"""
from __future__ import annotations
import json
import sys
import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env  # noqa: E402

load_env()


from nullrun import init_or_die, shutdown, set_call_context  # noqa: E402
from nullrun import get_runtime  # noqa: E402

init_or_die()
runtime = get_runtime()

# Provide tools context to avoid the no_tools_field tool_block default.
set_call_context(tools=["read_file"])

# Monkey-patch the Transport.check to log raw responses
from nullrun.transport import Transport  # noqa: E402

_original_check = Transport.check


def _patched_check(self, check_request, on_transport_error=None):
    print("---GATE-REQUEST---", flush=True)
    safe_req = {k: v for k, v in check_request.items() if k not in ("api_key", "hmac")}
    print(json.dumps(safe_req, indent=2, default=str), flush=True)
    result = _original_check(self, check_request, on_transport_error)
    print("---GATE-RESPONSE---", flush=True)
    print(json.dumps(result, indent=2, default=str), flush=True)
    return result


Transport.check = _patched_check  # type: ignore[method-assign]

print("---PROBE-RESULTS---")
try:
    runtime.check_workflow_budget()
    print("('allow', 0, None, None)")
except BaseException as e:
    code = getattr(e, "error_code", None) or getattr(e, "code", None)
    print(f"('block', 0, '{type(e).__name__}', {code!r})")
finally:
    set_call_context(tools=[])
    shutdown()
