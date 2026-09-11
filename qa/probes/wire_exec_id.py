"""
TC-SDKG-005: Server-minted execution_id — SDK sends client-minted id,
backend response contains different UUIDv7 (server-minted).

Endpoint migration (2026-09-10): POST /api/v1/check → POST /api/v1/gate.
The /check endpoint was removed in the v3 consolidation (2026-06-27)
and replaced by /gate; the test contract (client-supplied id ignored,
server returns a different uuidv7) is unchanged.
"""
from __future__ import annotations
import os
import json
import uuid
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")
WORKFLOW_ID = os.environ.get("NULLRUN_WORKFLOW_ID", "")
CLIENT_EXEC_ID = "11111111-1111-1111-1111-111111111111"


def main():
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-NULLRUN-PROTOCOL": "4",
        "Content-Type": "application/json",
    }
    body = {
        "workflow_id": WORKFLOW_ID,
        "tools": ["echo"],
        "estimated_tokens": 10,
        "model": "gpt-4o-mini",
        "execution_id": CLIENT_EXEC_ID,  # client-supplied, should be ignored
    }
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=headers, json=body, timeout=15)
    out = {"status": r.status_code}
    try:
        j = r.json()
        srv_exec_id = j.get("execution_id")
        out["server_execution_id"] = srv_exec_id
        out["client_execution_id"] = CLIENT_EXEC_ID
        out["different"] = srv_exec_id != CLIENT_EXEC_ID
        # UUIDv7 format check: first nibble is version (7)
        if srv_exec_id and len(srv_exec_id) == 36:
            version_char = srv_exec_id.split("-")[2][0]
            out["is_uuidv7"] = version_char == "7"
    except Exception as e:
        out["exception"] = str(e)[:200]
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
