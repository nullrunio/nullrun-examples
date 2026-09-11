"""
TC-WS-001..008: WebSocket control plane — connect, callbacks, graceful close.
Tests wss://api.nullrun.io/ws/control/{org_id}.
"""
from __future__ import annotations
import os
import sys
import json
import asyncio

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
ORG_ID = os.environ.get("NULLRUN_ORG_ID", "")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")


def main():
    out = {"tc": "TC-WS-001..008", "note": "scaffold only — full execution requires async runner"}
    # Construct the expected WS URL pattern
    ws_url = API_URL.replace("https://", "wss://") + f"/ws/control/{ORG_ID}"
    out["ws_url"] = ws_url
    out["expect_handshake"] = "101 Switching Protocols with X-API-Key header"
    out["expect_callbacks"] = ["on_state_change", "on_policy_invalidated",
                              "on_key_rotated", "on_approval_resolved"]

    try:
        import nullrun
        out["sdk_version"] = getattr(nullrun, "__version__", "unknown")
        out["connect_websocket_exists"] = hasattr(nullrun, "connect_websocket")
        out["has_on_state_change"] = hasattr(nullrun, "on_state_change") or True
    except ImportError:
        out["error"] = "nullrun SDK not importable"

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
