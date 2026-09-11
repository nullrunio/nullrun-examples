"""TC-3 raw-track probe: monkey-patch Transport.execute_batch to print
the raw response from /track, then drive runtime.track() to push a
synthetic cost_cents event. Use this to inspect why budget isn't
enforced end-to-end."""
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
set_call_context(tools=["read_file"])

# Monkey-patch Transport.execute_batch (the /track/batch endpoint)
from nullrun.transport import Transport  # noqa: E402

_original = Transport.execute_batch


def _patched(self, batch):
    print("---TRACK-REQUEST---", flush=True)
    print(json.dumps(batch, indent=2, default=str), flush=True)
    result = _original(self, batch)
    print("---TRACK-RESPONSE---", flush=True)
    print(json.dumps(result, indent=2, default=str), flush=True)
    return result


Transport.execute_batch = _patched  # type: ignore[method-assign]

print("---PROBE-RESULTS---")
try:
    runtime.track({
        "type": "tool_call",
        "tool_name": "read_file",
        "tokens": 0,
        "cost_cents": 10,
    })
    print("('allow', 0, None, None)")
except BaseException as e:
    code = getattr(e, "error_code", None) or getattr(e, "code", None)
    print(f"('block', 0, '{type(e).__name__}', {code!r})")
finally:
    set_call_context(tools=[])
    shutdown()
