"""
TS-12f SDK error transport probe (Sprint N+1 / 2026-08-27).

Verifies wire-shape behaviour of /api/v1/gate, /api/v1/track,
/api/v1/budget/approximate against the contract in CL/АUDE.md §13.

Critical regression targets:
 - DEF-SDKERR-WIRE-422-DESER-01 (Sprint N+1 ee72f550) — json_rejection.rs
 - DEF-SDK-WIRE-DRIFT-01 — server-minted execution_id
 - DEF-PRODPATH-12A-WIRE-503-EMPTY-01 — /track wire envelope

Usage:
    python qa/probes/ts12f/sdk_err_probe2.py [probe_name]

If no probe_name is given, runs all probes sequentially.

Reuses the test API key fetched via auth/verify on 2026-08-27.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from typing import Any

import httpx

# Load shared .env (examples/.env) — repo root is 4 dirs up: ts12f/ -> probes/ -> qa/ -> <root>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from examples._env import load_env  # type: ignore

load_env()

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ["NULLRUN_API_KEY"]
SECRET_KEY = os.environ.get("NULLRUN_API_SECRET", "")
ORG_ID = os.environ["NULLRUN_ORG_ID"]
WF_ID = os.environ["NULLRUN_WORKFLOW_ID"]


def _sign_body(body: bytes) -> dict[str, str]:
    ts = int(time.time())
    body_hash = hashlib.sha256(body).hexdigest()
    msg = f"{ts}:{API_KEY}:{body_hash}".encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return {
        "X-API-Key": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "X-Signature-Timestamp": str(ts),
        "X-Signature": sig,
        "Content-Type": "application/json",
    }


def _gate(body: dict[str, Any], protocol_version: int = 3, raw_body: bytes | None = None) -> dict[str, Any]:
    body_bytes = raw_body if raw_body is not None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = _sign_body(body_bytes)
    headers["X-NULLRUN-PROTOCOL"] = str(protocol_version)
    r = httpx.post(
        f"{API_URL}/api/v1/gate",
        content=body_bytes,
        headers=headers,
        timeout=10.0,
    )
    return {"status_code": r.status_code, "headers": dict(r.headers), "body": r.text, "json": _safe_json(r)}


def _track(body: dict[str, Any]) -> dict[str, Any]:
    body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = _sign_body(body_bytes)
    headers["X-NULLRUN-PROTOCOL"] = "3"
    r = httpx.post(
        f"{API_URL}/api/v1/track",
        content=body_bytes,
        headers=headers,
        timeout=10.0,
    )
    return {"status_code": r.status_code, "headers": dict(r.headers), "body": r.text, "json": _safe_json(r)}


def _track_batch(body: dict[str, Any]) -> dict[str, Any]:
    body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = _sign_body(body_bytes)
    headers["X-NULLRUN-PROTOCOL"] = "3"
    r = httpx.post(
        f"{API_URL}/api/v1/track/batch",
        content=body_bytes,
        headers=headers,
        timeout=10.0,
    )
    return {"status_code": r.status_code, "headers": dict(r.headers), "body": r.text, "json": _safe_json(r)}


def _approx() -> dict[str, Any]:
    ts = int(time.time())
    headers = {
        "X-API-Key": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "X-NULLRUN-PROTOCOL": "3",
    }
    r = httpx.get(f"{API_URL}/api/v1/budget/approximate", headers=headers, timeout=10.0)
    return {"status_code": r.status_code, "headers": dict(r.headers), "body": r.text, "json": _safe_json(r)}


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return None


def _print(label: str, result: dict[str, Any]) -> None:
    print(f"=== {label} ===")
    print(f"status_code: {result['status_code']}")
    print(f"content-type: {result['headers'].get('content-type', 'N/A')}")
    body = result["body"]
    if len(body) > 500:
        print(f"body[truncated 500]: {body[:500]}")
    else:
        print(f"body: {body}")
    print()


# Probe implementations
def p_no_proto() -> None:
    """TC-SDK-ERR-09: Missing X-NULLRUN-PROTOCOL header."""
    body_bytes = b'{"organization_id":"' + ORG_ID.encode() + b'","execution_id":"' + str(uuid.uuid4()).encode() + b'"}'
    headers = _sign_body(body_bytes)
    # Deliberately omit X-NULLRUN-PROTOCOL
    r = httpx.post(f"{API_URL}/api/v1/gate", content=body_bytes, headers=headers, timeout=10.0)
    _print("TC-SDK-ERR-09: missing X-NULLRUN-PROTOCOL", {
        "status_code": r.status_code, "headers": dict(r.headers), "body": r.text, "json": _safe_json(r),
    })


def p_wrong_proto() -> None:
    """TC-SDK-ERR-03 + TC-SDK-ERR-12: X-NULLRUN-PROTOCOL: 1 (too old)."""
    body = {"organization_id": ORG_ID, "execution_id": str(uuid.uuid4())}
    _print("TC-SDK-ERR-03/12: X-NULLRUN-PROTOCOL: 1 (too old)", _gate(body, protocol_version=1))


def p_invalid_json() -> None:
    """TC-SDK-ERR-16: Invalid JSON in /gate body — verify DEF-SDKERR-WIRE-422-DESER-01 FIXED."""
    body_bytes = b'{"invalid_json":'
    headers = _sign_body(body_bytes)
    headers["X-NULLRUN-PROTOCOL"] = "3"
    r = httpx.post(f"{API_URL}/api/v1/gate", content=body_bytes, headers=headers, timeout=10.0)
    _print("TC-SDK-ERR-16: invalid JSON body", {
        "status_code": r.status_code, "headers": dict(r.headers), "body": r.text, "json": _safe_json(r),
    })


def p_missing_field() -> None:
    """TC-SDK-ERR-17: Missing required field in /gate body — verify FIXED."""
    body_bytes = b"{}"
    headers = _sign_body(body_bytes)
    headers["X-NULLRUN-PROTOCOL"] = "3"
    r = httpx.post(f"{API_URL}/api/v1/gate", content=body_bytes, headers=headers, timeout=10.0)
    _print("TC-SDK-ERR-17: missing required field", {
        "status_code": r.status_code, "headers": dict(r.headers), "body": r.text, "json": _safe_json(r),
    })


def p_wrong_content_type() -> None:
    """TC-SDK-ERR-16b: Wrong Content-Type on /gate — should hit MissingJsonContentType path."""
    body_bytes = b'{"organization_id":"' + ORG_ID.encode() + b'"}'
    headers = _sign_body(body_bytes)
    headers["X-NULLRUN-PROTOCOL"] = "3"
    headers["Content-Type"] = "text/plain"
    r = httpx.post(f"{API_URL}/api/v1/gate", content=body_bytes, headers=headers, timeout=10.0)
    _print("TC-SDK-ERR-16b: Content-Type text/plain", {
        "status_code": r.status_code, "headers": dict(r.headers), "body": r.text, "json": _safe_json(r),
    })


def p_server_minted() -> None:
    """TC-SDK-ERR-10: Client-supplied execution_id IGNORED, server-minted used."""
    client_exec_id = "11111111-1111-1111-1111-111111111111"
    # Minimal valid gate body that should not trigger pre-flight reject
    body = {
        "organization_id": ORG_ID,
        "execution_id": client_exec_id,
        "trace_id": str(uuid.uuid4()),
        "tool": "noop",
        "mode": "auto",
        "check_type": "llm",
        "model": "gpt-4o-mini",
        "operation_id": str(uuid.uuid4()),
    }
    r = _gate(body)
    print("=== TC-SDK-ERR-10: client execution_id (must be server-minted only) ===")
    print(f"status_code: {r['status_code']}")
    print(f"client supplied: {client_exec_id}")
    print(f"body: {r['body'][:600]}")
    if r.get("json") and isinstance(r["json"], dict):
        reservation_id = r["json"].get("reservation_id")
        if reservation_id:
            uuid_obj = uuid.UUID(reservation_id)
            print(f"reservation_id: {reservation_id}, variant={uuid_obj.version}")
            if uuid_obj.version == 7:
                print("OK: server-minted UUIDv7")
            else:
                print(f"WARN: server returned UUIDv{uuid_obj.version}, not v7")
    print()


def p_approximate_budget() -> None:
    """TC-SDK-ERR-08: /api/v1/budget/approximate 503 + retry_after_ms — verify §17."""
    _print("TC-SDK-ERR-08: /budget/approximate", _approx())


def p_track_empty_body() -> None:
    """TC-SDK-ERR-11ish: /track with omitted required fields."""
    body = {"organization_id": ORG_ID}
    _print("TC-SDK-ERR-11 track (no reservation_id)", _track(body))


def p_revoked_key() -> None:
    """TC-SDK-ERR-04: API_KEY_REVOKED check via bogus key."""
    body_bytes = b"{}"
    headers = {
        "X-API-Key": "nr_live_" + "x" * 40,
        "Authorization": "Bearer nr_live_" + "x" * 40,
        "X-NULLRUN-PROTOCOL": "3",
        "Content-Type": "application/json",
    }
    r = httpx.post(f"{API_URL}/api/v1/gate", content=body_bytes, headers=headers, timeout=10.0)
    _print("TC-SDK-ERR-04: bogus api key", {
        "status_code": r.status_code, "headers": dict(r.headers), "body": r.text, "json": _safe_json(r),
    })


PROBES: dict[str, Any] = {
    "no_proto": p_no_proto,
    "wrong_proto": p_wrong_proto,
    "invalid_json": p_invalid_json,
    "missing_field": p_missing_field,
    "wrong_content_type": p_wrong_content_type,
    "server_minted": p_server_minted,
    "approximate_budget": p_approximate_budget,
    "track_empty_body": p_track_empty_body,
    "revoked_key": p_revoked_key,
}


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        probe_name = argv[1]
        if probe_name not in PROBES:
            print(f"unknown probe: {probe_name}. choices: {list(PROBES.keys())}")
            return 2
        PROBES[probe_name]()
        return 0
    for name, fn in PROBES.items():
        fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
