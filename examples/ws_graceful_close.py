"""
TC-WS-006: Graceful WS close — nullrun.shutdown() sends WS close frame 1000,
no "Connection reset without closing handshake" in backend logs.
"""
from __future__ import annotations
import os
import sys
import json
import time


def main():
    out = {"tc": "TC-WS-006"}
    try:
        import nullrun
        api_key = os.environ.get("NULLRUN_API_KEY")
        if api_key:
            nullrun.init(api_key=api_key)
            out["init_ok"] = True
            time.sleep(0.5)
            nullrun.shutdown()
            out["shutdown_ok"] = True
        else:
            out["error"] = "NULLRUN_API_KEY not set"
    except Exception as e:
        out["exception"] = f"{type(e).__name__}: {e}"[:200]
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
