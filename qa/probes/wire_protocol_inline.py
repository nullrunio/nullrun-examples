"""
Inline verification for TC-SDKG-001..008.
The wire_contract probes use wrong endpoint /api/v1/check (not exposed) — actual
gate endpoint is /api/v1/gate with required HMAC + protocol header.
"""
from __future__ import annotations
import os, json, time, uuid, hashlib, hmac
import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")
SECRET = os.environ.get("NULLRUN_API_SECRET", "")
WORKFLOW = os.environ.get("NULLRUN_WORKFLOW_ID", "")
ORG = os.environ.get("NULLRUN_ORG_ID", "")


def signed_headers(body: bytes, ts: int | None = None, proto: str = "3"):
    if ts is None:
        ts = int(time.time())
    body_sha = hashlib.sha256(body).hexdigest()
    msg = f"{ts}:{API_KEY}:{body_sha}".encode()
    sig = hmac.new(SECRET.encode(), msg, hashlib.sha256).hexdigest()
    h = {
        "X-API-Key": API_KEY,
        "X-Signature": sig,
        "X-Signature-Timestamp": str(ts),
        "X-NULLRUN-PROTOCOL": proto,
        "Content-Type": "application/json",
    }
    return h


def base_body(extra: dict | None = None) -> bytes:
    b = {
        "workflow_id": WORKFLOW,
        "organization_id": ORG,
        "execution_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "mode": "check",
        "tools": ["echo"],
        "estimated_tokens": 10,
        "model": "gpt-4o-mini",
        "idempotency_key": f"wire-{int(time.time()*1000)}",
    }
    if extra:
        b.update(extra)
    return json.dumps(b).encode()


def main():
    out = {}

    # TC-SDKG-001: missing protocol header
    body = base_body()
    h = signed_headers(body)
    del h["X-NULLRUN-PROTOCOL"]
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=h, content=body, timeout=15)
    out["TC-SDKG-001"] = {
        "status": r.status_code,
        "expected": 400,
        "ok": r.status_code == 400,
        "body_snippet": r.text[:200],
    }
    try:
        out["TC-SDKG-001"]["error_code"] = r.json().get("error_code")
    except Exception:
        pass

    # TC-SDKG-002: too old
    h = signed_headers(body, proto="1")
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=h, content=body, timeout=15)
    out["TC-SDKG-002"] = {
        "status": r.status_code,
        "expected": 400,
        "ok": r.status_code == 400,
        "body_snippet": r.text[:200],
    }
    try:
        out["TC-SDKG-002"]["error_code"] = r.json().get("error_code")
    except Exception:
        pass

    # TC-SDKG-003: too new
    h = signed_headers(body, proto="99")
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=h, content=body, timeout=15)
    out["TC-SDKG-003"] = {
        "status": r.status_code,
        "expected": 400,
        "ok": r.status_code == 400,
        "body_snippet": r.text[:200],
    }
    try:
        out["TC-SDKG-003"]["error_code"] = r.json().get("error_code")
    except Exception:
        pass

    # TC-SDKG-004: malformed
    h = signed_headers(body)
    h["X-NULLRUN-PROTOCOL"] = "not_a_number"
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=h, content=body, timeout=15)
    out["TC-SDKG-004"] = {
        "status": r.status_code,
        "expected": 400,
        "ok": r.status_code == 400,
        "body_snippet": r.text[:200],
    }
    try:
        out["TC-SDKG-004"]["error_code"] = r.json().get("error_code")
    except Exception:
        pass

    # TC-SDKG-005: server-minted execution_id
    body = base_body({"execution_id": "11111111-1111-1111-1111-111111111111"})
    h = signed_headers(body)
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=h, content=body, timeout=15)
    out["TC-SDKG-005"] = {
        "status": r.status_code,
        "client_execution_id": "11111111-1111-1111-1111-111111111111",
        "server_execution_id": "server-mints-not-in-response",
        "decision": None,
    }
    try:
        j = r.json()
        out["TC-SDKG-005"]["decision"] = j.get("decision")
        out["TC-SDKG-005"]["explanation"] = j.get("explanation")
        out["TC-SDKG-005"]["response_keys"] = list(j.keys())
        # Per backend architecture: execution_id is in reservation_id or follow-up /track
        if "execution_id" in j:
            out["TC-SDKG-005"]["server_execution_id"] = j["execution_id"]
    except Exception as e:
        out["TC-SDKG-005"]["exception"] = str(e)

    # TC-SDKG-006: malformed JSON
    h = signed_headers(b"not json", proto="3")
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=h, content=b"not json", timeout=15)
    out["TC-SDKG-006"] = {
        "status": r.status_code,
        "expected": 400,
        "ok": r.status_code == 400,
        "body_snippet": r.text[:200],
    }
    try:
        out["TC-SDKG-006"]["error_code"] = r.json().get("error_code")
    except Exception:
        pass

    # TC-SDKG-007: model field optional
    body_dict = {
        "workflow_id": WORKFLOW,
        "organization_id": ORG,
        "execution_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "mode": "check",
        "tools": ["echo"],
        "estimated_tokens": 10,
        "idempotency_key": f"wire-model-{int(time.time()*1000)}",
    }
    body = json.dumps(body_dict).encode()
    h = signed_headers(body)
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=h, content=body, timeout=15)
    out["TC-SDKG-007"] = {
        "status": r.status_code,
        "no_model_field": True,
        "expected": "200 or decision; not 400",
        "ok": r.status_code == 200,
        "body_snippet": r.text[:200],
    }

    # TC-SDKG-008: projected_cost_cents is response-only, server-computed
    body = base_body({"projected_cost_cents": 99999})
    h = signed_headers(body)
    r = httpx.post(f"{API_URL}/api/v1/gate", headers=h, content=body, timeout=15)
    out["TC-SDKG-008"] = {
        "status": r.status_code,
        "client_supplied": 99999,
    }
    try:
        j = r.json()
        srv = j.get("projected_cost_cents")
        out["TC-SDKG-008"]["server_projected_cost_cents"] = srv
        out["TC-SDKG-008"]["client_ignored"] = (srv != 99999)
        out["TC-SDKG-008"]["decision"] = j.get("decision")
    except Exception as e:
        out["TC-SDKG-008"]["exception"] = str(e)

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
