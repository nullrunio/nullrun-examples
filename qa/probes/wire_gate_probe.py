"""wire_gate_probe.py — Direct /api/v1/gate HMAC-signed wire probe.

Per SDK_TEST §6, all gate requests must carry X-NULLRUN-PROTOCOL=4 +
HMAC signature (X-API-Key, X-Signature, X-Signature-Timestamp).
The current workflow 82dc8b59-... is in BudgetPressure trip (NOT hard-killed)
so /gate still returns Allow for tool-name-only checks (no LLM tokens consumed).

Usage as a library:
    from wire_gate_probe import probe_gate
    verdict, body, headers = probe_gate(tools=['search_web'], model='gpt-4o-mini')

Returns: (http_status: int, json_or_text, response_headers)
"""
from __future__ import annotations
import os, sys, json, time, hmac, hashlib, urllib.request, urllib.error
from pathlib import Path


def _load_env(env_path: str = "../examples/.env") -> dict:
    env = {}
    p = Path(env_path)
    if not p.exists():
        p = Path(__file__).resolve().parent.parent.parent / "examples" / ".env"
    if not p.exists():
        p = Path("C:/Users/Anatolii Maltsev/Documents/AGENTIC/nullrun-examples/examples/.env")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


_ENV = _load_env()
API_KEY = _ENV.get("NULLRUN_API_KEY", "")
API_SECRET = _ENV.get("NULLRUN_API_SECRET", "")
ORG_ID = _ENV.get("NULLRUN_ORG_ID", "")
WF_ID = _ENV.get("NULLRUN_WORKFLOW_ID", "")
API_URL = _ENV.get("NULLRUN_API_URL", "https://api.nullrun.io").rstrip("/")


def _sign(body: bytes, ts: str | None = None) -> tuple[str, str]:
    ts = ts or str(int(time.time()))
    msg = f"{ts}:{API_KEY}:{hashlib.sha256(body).hexdigest()}"
    sig = hmac.new(API_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return ts, sig


def _compute_action_digest(impact: dict) -> str:
    """Mirror of nullrun-sdk-python/src/nullrun/business_impact.py::compute_action_digest.

    Canonical JSON (sorted keys, compact separators) + SHA-256 with prefix
    b'nullrun/v1/business_impact:'.
    """
    def canon(v):
        if isinstance(v, dict):
            return {k: canon(val) for k, val in sorted(v.items())}
        if isinstance(v, list):
            return [canon(x) for x in v]
        return v
    canonical = canon(impact)
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=False).encode("utf-8")
    h = hashlib.sha256()
    h.update(b"nullrun/v1/business_impact:")
    h.update(payload)
    return h.hexdigest()


def probe_gate(
    *,
    tools: list[str] | None = None,
    tool_name: str | None = None,
    model: str | None = None,
    estimated_tokens: int | None = None,
    estimated_cost_cents: int | None = None,
    organization_id: str | None = None,
    workflow_id: str | None = None,
    session_id: str | None = None,
    execution_id: str | None = None,
    chain_id: str | None = None,
    trace_id: str | None = None,
    mode: str | None = None,
    action_impact: dict | None = None,
    no_action_digest: bool = False,
    extra_body: dict | None = None,
    ts: str | None = None,
    protocol: int = 4,
    method: str = "POST",
    path: str = "/api/v1/gate",
    body_override: bytes | None = None,
) -> tuple[int, dict | str, dict]:
    """Send one signed /api/v1/gate (or /api/v1/track) request.

    Returns (http_status, json_or_text, response_headers_dict).
    """
    import uuid
    org_id = organization_id or ORG_ID
    wf_id = workflow_id or WF_ID

    body_dict: dict = {
        "organization_id": org_id,
        "workflow_id": wf_id,
        "mode": mode or "check",
        "trace_id": trace_id or str(uuid.uuid4()),
        "execution_id": execution_id or str(uuid.uuid4()),
    }
    if tool_name:
        body_dict["tool_name"] = tool_name
    if tools:
        body_dict["tools"] = tools
    if model:
        body_dict["model"] = model
    if estimated_tokens is not None:
        body_dict["estimated_tokens"] = estimated_tokens
    if estimated_cost_cents is not None:
        body_dict["estimated_cost_cents"] = estimated_cost_cents
    if session_id:
        body_dict["session_id"] = session_id
    if chain_id:
        body_dict["chain_id"] = chain_id
    if action_impact and not no_action_digest:
        body_dict["action_digest"] = _compute_action_digest(action_impact)
        body_dict["impact"] = action_impact
    if extra_body:
        body_dict.update(extra_body)

    body = body_override if body_override is not None else json.dumps(body_dict).encode()
    ts_s, sig = _sign(body, ts=ts)

    url = API_URL + path
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "X-API-Key": API_KEY,
            "X-Signature": sig,
            "X-Signature-Timestamp": ts_s,
            "X-NULLRUN-PROTOCOL": str(protocol),
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            text = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(text), dict(r.headers)
            except json.JSONDecodeError:
                return r.status, text, dict(r.headers)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(text), dict(e.headers)
        except json.JSONDecodeError:
            return e.code, text, dict(e.headers)
    except Exception as e:
        return 0, str(e), {}


def probe_track(*, execution_id: str, actual_cost_cents: int, **kwargs) -> tuple[int, dict | str, dict]:
    """Send one /api/v1/track call (server-minted execution_id required)."""
    return probe_gate(
        path="/api/v1/track",
        extra_body={
            "execution_id": execution_id,
            "actual_cost_cents": actual_cost_cents,
        },
        **kwargs,
    )


if __name__ == "__main__":
    # Quick self-test
    status, body, hdrs = probe_gate(tools=["search_web"])
    print(f"GET /api/v1/gate (tools=['search_web']) → HTTP {status}")
    print(f"  body: {str(body)[:300]}")
    print(f"  X-NULLRUN-DECISION-ID: {hdrs.get('X-NULLRUN-DECISION-ID', hdrs.get('x-nullrun-decision-id', '?'))}")
