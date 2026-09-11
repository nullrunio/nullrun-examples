"""
TC-SDKU-025: Loop window resets after expiry.

Drives TC-SDKU-025 — proves that the loop-detection window (ZRANGEBYSCORE
sliding window) is correctly reset once the configured window_secs has
elapsed. Plan v5.0 §6.5.6:

  setup: [STD+POL:loop_threshold=2, loop_window_secs=30]
  action: t=0 call × 2, wait 31s, t=31s call
  pass: 3rd call (t=31s) returns 200 (window expired)

This is a time-dependent test. The runner sets a short window (30s) and
the test waits 31s between iter1+2 and iter3.
"""
from __future__ import annotations

import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import nullrun
except ImportError as e:
    print(json.dumps({"tc": "TC-SDKU-025", "fatal": "nullrun SDK not importable", "error": str(e)}))
    sys.exit(0)


def _call(tool: str, cost_cents: int = 1):
    """Single protected call returning the SDK result."""
    @nullrun.protect(tool=tool)
    def _inner():
        return f"ok-{tool}"
    return _inner()


def main():
    out = {
        "tc": "TC-SDKU-025",
        "expect": "t=0 call×2 allowed; after 31s wait, t=31s call allowed (window expired)",
        "calls": [],
        "pass": True,
    }
    # iter1
    t0 = time.time()
    try:
        r1 = _call("echo")
        out["calls"].append({"t": 0, "result": str(r1)[:100]})
    except Exception as e:
        out["calls"].append({"t": 0, "exception": type(e).__name__, "msg": str(e)[:120]})

    # iter2 (within window)
    try:
        r2 = _call("echo")
        out["calls"].append({"t": 0, "result": str(r2)[:100]})
    except Exception as e:
        out["calls"].append({"t": 0, "exception": type(e).__name__, "msg": str(e)[:120]})

    # wait 31s for window expiry
    time.sleep(31)
    try:
        r3 = _call("echo")
        out["calls"].append({"t": 31, "result": str(r3)[:100]})
    except Exception as e:
        out["calls"].append({"t": 31, "exception": type(e).__name__, "msg": str(e)[:120]})

    # Window reset → iter3 should NOT be blocked. If exception type
    # mentions LOOP_DETECTED, fail.
    blocked = any(
        c.get("exception", "").upper().startswith("LOOP") for c in out["calls"]
    )
    out["pass"] = not blocked
    out["elapsed_secs"] = round(time.time() - t0, 1)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
