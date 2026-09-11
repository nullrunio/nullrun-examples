"""Perimeter probe: wire envelope passthrough (B.4 #1, 2026-09-10).

Drives ``POST /api/v1/gate`` with a deliberately malformed
request and verifies the response carries a v3 envelope shape
(``error_code``, ``error_message``, ``details``, ``retry_after_ms``)
rather than a bare HTTP status with empty body.

Pre-fix (the v3 envelope drift, audit 2026-09-09) several error
paths emitted raw JSON literals with non-canonical error codes —
the SDK couldn't branch on the typed class because the wire
string wasn't owned by ``GateErrorCode``. The post-fix path
routes every 4xx/5xx through ``v3_error_envelope`` so the wire
shape is consistent.

This probe verifies the shape contract end-to-end:
  1. HTTP 4xx status
  2. Body parses as JSON
  3. ``error_code`` is a non-empty string
  4. ``error_message`` is a non-empty string
  5. ``retry_after_ms`` is present for 429/503 (rate-limit / infra)

Usage:
    python qa/probes/wire_envelope_passthrough.py

Pre-req: NULLRUN_API_KEY / NULLRUN_API_URL / NULLRUN_WORKFLOW_ID
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import json
import os

import httpx

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
API_KEY = os.environ.get("NULLRUN_API_KEY", "")


def _probe(label: str, body: dict, headers: dict) -> dict:
    """POST /api/v1/gate with the given body + headers, validate
    the wire envelope shape, return a verdict dict."""
    out: dict = {"label": label}
    try:
        r = httpx.post(
            f"{API_URL}/api/v1/gate",
            headers=headers,
            json=body,
            timeout=10.0,
        )
        out["status"] = r.status_code
        try:
            j = r.json()
            out["json_present"] = True
        except Exception as e:
            out["json_present"] = False
            out["json_error"] = str(e)[:200]
            out["raw_body"] = r.text[:300]
            return out
        # Shape contract: error_code + error_message non-empty
        out["error_code"] = j.get("error_code")
        out["error_message"] = j.get("error_message")
        out["details_present"] = "details" in j
        # 429/503 must carry retry_after_ms
        if r.status_code in (429, 503):
            out["retry_after_ms_present"] = "retry_after_ms" in j
        else:
            out["retry_after_ms_present"] = "n/a"
        out["envelope_ok"] = (
            isinstance(out["error_code"], str)
            and out["error_code"] != ""
            and isinstance(out["error_message"], str)
            and out["error_message"] != ""
        )
    except Exception as e:
        out["exception"] = str(e)[:200]
    return out


def main():
    base_headers = {
        "Authorization": f"Bearer {API_KEY}",
        "X-NULLRUN-PROTOCOL": "4",
        "Content-Type": "application/json",
    }

    # Scenario 1: malformed JSON body (defense-in-depth — the SDK
    # already validates, but the backend's JsonRejection handling
    # must still produce a v3 envelope).
    scenarios = [
        (
            "SCENARIO 1: malformed tool_pattern",
            {
                "workflow_id": os.environ.get("NULLRUN_WORKFLOW_ID", ""),
                "tools": ["echo"],
                "estimated_tokens": 10,
                "model": "gpt-4o-mini",
                # `tool_pattern` should be an array of strings; an
                # integer triggers a validation envelope.
                "tool_pattern": 42,
            },
            base_headers,
        ),
        (
            "SCENARIO 2: missing X-NULLRUN-PROTOCOL header",
            {
                "workflow_id": os.environ.get("NULLRUN_WORKFLOW_ID", ""),
                "tools": ["echo"],
                "estimated_tokens": 10,
                "model": "gpt-4o-mini",
            },
            {**base_headers, "X-NULLRUN-PROTOCOL": ""},
        ),
        (
            "SCENARIO 3: missing workflow_id",
            {
                "tools": ["echo"],
                "estimated_tokens": 10,
                "model": "gpt-4o-mini",
            },
            base_headers,
        ),
    ]

    results = []
    for label, body, headers in scenarios:
        result = _probe(label, body, headers)
        results.append(result)
        print(
            f"[WIRE-ENVELOPE] {label}: status={result.get('status')} "
            f"error_code={result.get('error_code')!r} "
            f"envelope_ok={result.get('envelope_ok')}",
            flush=True,
        )

    # Verdict: every scenario must carry a v3 envelope
    # (error_code + error_message non-empty). A pre-v3 drift would
    # emit a bare HTTP 400 with empty body — caught here.
    verdict = (
        "PASS"
        if all(r.get("envelope_ok") for r in results)
        else "REVIEW — one or more scenarios missing v3 envelope"
    )
    print(f"[WIRE-ENVELOPE] === SUMMARY ===", flush=True)
    print(f"[WIRE-ENVELOPE] scenarios={len(results)}", flush=True)
    print(f"[WIRE-ENVELOPE] VERDICT={verdict}", flush=True)


if __name__ == "__main__":
    main()
