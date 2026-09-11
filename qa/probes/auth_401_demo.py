"""Probe for TC-23 — authentication failure (revoked/invalid API key)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "examples"))
try:
    from _env import load_env
    load_env()
except Exception:
    pass

# Override with clearly-invalid API key for this probe
os.environ["NULLRUN_API_KEY"] = "nr_live_invalid_key_aaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
os.environ.pop("NULLRUN_SECRET_KEY", None)

from nullrun.runtime import NullRunRuntime  # noqa: E402
from nullrun.context import set_call_context  # noqa: E402


def main() -> int:
    # Reset singleton so our bad key gets picked up
    try:
        NullRunRuntime.reset_instance()
    except Exception:
        pass
    try:
        rt = NullRunRuntime(
            api_key="nr_live_invalid_key_aaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            api_url=os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io"),
        )
        # SDK raised during __init__ → NullRunAuthenticationError not raised at __init__ level
        # We expect _authenticate() to throw — it doesn't always, depends on version.
        set_call_context(model="gpt-4o-mini", tools=("read_file",))

        try:
            rt.check_workflow_budget()
            print("GATE_OK (unexpected!)", flush=True)
        except Exception as e:
            print(f"GATE_FAIL: {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        # Auth failed during __init__ — fail-CLOSED, this is correct
        print(f"INIT_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
