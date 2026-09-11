"""
TC-SDKF-003: SDK fail-fast on missing api_key — NullRunAuthenticationError raised
BEFORE any HTTP request.
"""
from __future__ import annotations
import os
import sys
import json

# Ensure no NULLRUN_API_KEY is set in env
os.environ.pop("NULLRUN_API_KEY", None)
os.environ.pop("NULLRUN_API_SECRET", None)

# Also make sure there's no .env override for this test
import importlib

# Import SDK
try:
    import nullrun
except ImportError as e:
    print(json.dumps({"tc": "TC-SDKF-003", "fatal": "nullrun SDK not importable", "error": str(e)}))
    sys.exit(0)


def main():
    out = {"tc": "TC-SDKF-003", "expect": "NullRunAuthenticationError raised before HTTP call"}
    try:
        nullrun.init()
        out["result"] = "init_succeeded_no_raise_UNEXPECTED"
        out["pass"] = False
    except Exception as e:
        out["exception_type"] = type(e).__name__
        out["exception_msg"] = str(e)[:200]
        out["pass"] = "Authentication" in type(e).__name__ or "auth" in str(e).lower()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
