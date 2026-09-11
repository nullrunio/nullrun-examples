"""EDGE-NET-TIMEOUT test: simulate /check timeout mid-call.

We can't directly induce a network timeout on the live production endpoint,
but we can test the SDK's fail-OPEN behavior on transport errors by passing
an invalid API URL (which causes immediate DNS failure / connection refused).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from examples._env import load_env  # type: ignore

load_env()


def main():
    # Use a non-existent API URL to simulate network timeout
    # Set env vars BEFORE importing nullrun
    os.environ["NULLRUN_API_URL"] = "https://nullrun-does-not-exist-987654321.invalid"
    os.environ["NULLRUN_API_KEY"] = "nr_live_fakekey0000000000000000000000000000"

    # Reload nullrun with the new env
    import importlib
    import nullrun

    importlib.reload(nullrun)

    from nullrun import init, get_runtime, shutdown
    from nullrun.breaker.exceptions import (
        WorkflowKilledInterrupt,
        NullRunError,
        NullRunAuthenticationError,
    )

    try:
        init()
        print("Init result: OK (unexpected)")
    except NullRunAuthenticationError as e:
        # Auth happens first; if API key is fake it fails auth before networking
        print(f"Init raised NullRunAuthenticationError (expected for fake key): {str(e)[:120]}")
        return
    except Exception as e:
        print(f"Init raised {type(e).__name__}: {str(e)[:120]}")

    # If init succeeded (network reached but auth may have worked?), try check
    runtime = get_runtime()
    start = time.monotonic()
    try:
        result = runtime.check_workflow_budget()
        print(f"check_workflow_budget returned: {result} (elapsed={time.monotonic()-start:.2f}s)")
    except WorkflowKilledInterrupt as e:
        print(f"WorkflowKilledInterrupt (elapsed={time.monotonic()-start:.2f}s): {str(e)[:120]}")
    except NullRunError as e:
        print(f"NullRunError (elapsed={time.monotonic()-start:.2f}s): {str(e)[:120]}")
    except Exception as e:
        print(f"Other exception (elapsed={time.monotonic()-start:.2f}s): {type(e).__name__}: {str(e)[:120]}")

    shutdown()


if __name__ == "__main__":
    main()