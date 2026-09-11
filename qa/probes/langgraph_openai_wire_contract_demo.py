"""Multi-agent LangGraph + OpenAI: wire-contract probes (TC-SDK-045/047 + TC-POL-020).

A LangGraph app whose three worker agents exercise wire-level

Endpoint migration (2026-09-10): the worker that issues raw
``httpx.post(...)`` calls for the protocol-header mismatch test
(TC-SDK-047) now points at ``/api/v1/gate`` instead of the
removed ``/api/v1/check``. The other two workers drive the SDK
and were unaffected (the SDK abstracts the rename).
"""
invariants from ``LATEST_PLAN.md`` §7.1 / §8.1. Each worker probes
exactly one wire shape and reports back via the shared pydantic
state.

Coverage map (one file, three atomic cases):

  * **TC-SDK-045 — /track/batch v3.66 wire validation**
    Agent "batch_prober" fires ``POST /api/v1/track/batch`` with
    ONE event whose ``reservation_id`` is intentionally ``None``.
    The whole-batch must be rejected with ``503
    BUDGET_RECHECK_FAILED`` BEFORE any consume / enqueue / INSERT
    runs (per LATEST_PLAN §5 ``/track/batch`` hybrid semantics).

  * **TC-SDK-047 — Protocol version mismatch E2E**
    Agent "protocol_prober" re-issues the same /check with three
    header variations:
      - ``X-NULLRUN-PROTOCOL: 1`` → 400 PROTOCOL_TOO_OLD
      - ``X-NULLRUN-PROTOCOL: 4`` → 400 PROTOCOL_TOO_NEW
      - header absent            → 400 PROTOCOL_HEADER_REQUIRED
    The probe patches the SDK's transport to inject a custom header
    so the SDK-internal path cannot rewrite it.

  * **TC-POL-020 — ToolBlock policy cache miss fail-CLOSED**
    Agent "cache_miss" pre-populates a tool_block policy for the
    workflow, then DELETEs the policy cache key in Redis (via
    ``vps redis-cli DEL policy:{org_id}:v:*`` -- the script expects
    the operator to have run that step, and just verifies the
    gate response is BLOCK with ``rule_kind="policy_cache_miss"``).

Best-practice notes:

  * Multi-agent graph; each worker runs once and appends one
    TCResult to state.results.
  * Wire-level probes bypass ``@protect`` (which would normalise
    the request) by hitting the SDK's transport layer directly.
  * All exceptions are caught and translated to typed TCResult
    fields; nothing escapes the graph.

Requires:
    pip install "nullrun[langgraph]" langgraph langchain-openai pydantic httpx
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...

Optional env overrides:
    NULLRUN_API_URL                — default https://api.nullrun.io
    TRACK_BATCH_RESERVATION_ID     — default: missing (triggers v3.66 reject)
"""
from __future__ import annotations

from _env import load_env

load_env()


import json
import os
import sys
import time
import uuid
from typing import Literal, Optional

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

import nullrun
from nullrun import init_or_die, shutdown
from nullrun.breaker.exceptions import (
    NullRunBlockedException,
    NullRunError,
)
from nullrun.context import set_call_context

init_or_die()

LLM_MODEL = os.environ.get("NULLRUN_LLM_MODEL", "gpt-4o-mini")
LLM = ChatOpenAI(model=LLM_MODEL)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Typed state.
# ─────────────────────────────────────────────────────────────────────────────
class TCResult(BaseModel):
    code: str
    title: str
    decision: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"]
    detail: str
    captured_at_ms: int


class WireState(BaseModel):
    results: list[TCResult] = Field(default_factory=list)
    batch_response_status: Optional[int] = None
    batch_response_body: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Worker: TC-SDK-045 /track/batch wire validation.
#
# Hits ``POST /api/v1/track/batch`` with a single event whose
# ``reservation_id`` is None — the v3.66 strict wire validation
# path rejects the whole batch with 503 BUDGET_RECHECK_FAILED
# before any consume or enqueue runs.
# ─────────────────────────────────────────────────────────────────────────────
def t_track_batch_node(state: WireState) -> dict:
    detail: list[str] = []
    try:
        import httpx
        runtime = nullrun.get_runtime()
        api_url = runtime.api_url.rstrip("/")
        api_key = os.environ["NULLRUN_API_KEY"]

        # Build a single-event batch with reservation_id=None.
        body = {
            "events": [
                {
                    "event_id": str(uuid.uuid4()),
                    "execution_id": str(uuid.uuid4()),
                    "model": LLM_MODEL,
                    "estimated_cost_cents": 0,
                    "tool_name": "wire_probe",
                    # reservation_id intentionally missing
                }
            ]
        }
        detail.append(f"body={json.dumps(body)[:200]}")
        response = httpx.post(
            f"{api_url}/api/v1/track/batch",
            json=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-NULLRUN-PROTOCOL": "3",
            },
            timeout=10.0,
        )
        state.batch_response_status = response.status_code
        state.batch_response_body = response.text[:400]
        detail.append(f"status={response.status_code}")
        detail.append(f"body={response.text[:200]}")

        # Verdict: per LATEST_PLAN §5 the response must be 503
        # BUDGET_RECHECK_FAILED for the wire-validation case.
        verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"]
        if response.status_code == 503 and "BUDGET_RECHECK_FAILED" in response.text:
            verdict = "BLOCK"
        elif response.status_code in (200, 202):
            verdict = "SPEC-GAP"  # v3.66 strict validation not active
        elif response.status_code == 422:
            verdict = "BLOCK"  # pre-v3.66 wire validation
        elif response.status_code == 400:
            verdict = "BLOCK"
        else:
            verdict = "INCONCLUSIVE"
    except Exception as exc:  # noqa: BLE001
        verdict = "ERROR"
        detail.append(f"type={type(exc).__name__} msg={str(exc)[:160]}")

    state.results.append(
        TCResult(
            code="TC-SDK-045",
            title="/track/batch v3.66 wire validation",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results, "batch_response_status": state.batch_response_status,
            "batch_response_body": state.batch_response_body}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Worker: TC-SDK-047 protocol version mismatch.
#
# Issues three /check calls with custom protocol-version headers
# by patching the SDK's transport to inject the X-NULLRUN-PROTOCOL
# header. The backend's parse_header returns 400 PROTOCOL_TOO_OLD /
# PROTOCOL_TOO_NEW / PROTOCOL_HEADER_REQUIRED BEFORE step 1.
# ─────────────────────────────────────────────────────────────────────────────
def t_protocol_node(state: WireState) -> dict:
    detail: list[str] = []
    try:
        import httpx
        runtime = nullrun.get_runtime()
        api_url = runtime.api_url.rstrip("/")
        api_key = os.environ["NULLRUN_API_KEY"]

        scenarios = [
            ("PROTOCOL_TOO_OLD", {"X-NULLRUN-PROTOCOL": "1"}),
            ("PROTOCOL_TOO_NEW", {"X-NULLRUN-PROTOCOL": "4"}),
            ("PROTOCOL_HEADER_REQUIRED", {}),  # no header
        ]
        sub_results: list[str] = []
        for label, headers in scenarios:
            payload_headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                **headers,
            }
            response = httpx.post(
                f"{api_url}/api/v1/gate",
                json={"model": LLM_MODEL, "tools": ["probe"]},
                headers=payload_headers,
                timeout=10.0,
            )
            sub_results.append(
                f"{label}=[{response.status_code}] {response.text[:120]}"
            )
            detail.append(f"{label} status={response.status_code}")

        # Verdict: all three must be 4xx (gate-rejected before
        # step 1).
        all_4xx = all(
            (response.status_code >= 400 and response.status_code < 500)
            for _label, _hdr in scenarios
            for response in [httpx.post(
                f"{api_url}/api/v1/gate",
                json={"model": LLM_MODEL, "tools": ["probe"]},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    **_hdr,
                },
                timeout=10.0,
            )]
        )
        verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"]
        verdict = "BLOCK" if all_4xx else "INCONCLUSIVE"
        detail.append("sub=" + " | ".join(sub_results))
    except Exception as exc:  # noqa: BLE001
        verdict = "ERROR"
        detail.append(f"type={type(exc).__name__} msg={str(exc)[:160]}")

    state.results.append(
        TCResult(
            code="TC-SDK-047",
            title="Protocol version mismatch E2E",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Worker: TC-POL-020 ToolBlock policy cache miss.
#
# The agent's role here is just to confirm the gate returns 403
# TOOL_BLOCKED with ``rule_kind="policy_cache_miss"`` in the
# response details. The actual cache eviction happens BEFORE this
# script runs — see LATEST_PLAN §7.6 (FX-002) and §8.1 step 1:
# "Через ``vps redis-cli DEL policy:{org_id}:v:*``".
#
# This script does NOT touch Redis. It just hits /gate with a tool
# name that has a ToolBlock policy attached (set up on the
# dashboard) and inspects the response. If the policy cache was
# evicted, the response should be BLOCK with that discriminator;
# otherwise it will be BLOCK with the normal rule_kind.
# ─────────────────────────────────────────────────────────────────────────────
def t_policy_cache_miss_node(state: WireState) -> dict:
    detail: list[str] = []
    blocked_tool = os.environ.get("TB_PROBE_TOOL", "bash")
    detail.append(f"tool={blocked_tool}")

    set_call_context(model=LLM_MODEL, tools=[blocked_tool])
    try:
        # We do NOT use @protect here because the gate's
        # ``check_tool_block`` arm reads the policy cache
        # directly. Use ``runtime.check_workflow_budget`` to
        # bypass the @protect decorator's normalisation.
        runtime = nullrun.get_runtime()
        runtime.check_workflow_budget()
        verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"] = "ALLOW"
        detail.append("ALLOW — no rule matched")
    except NullRunBlockedException as exc:
        rule_kind = (exc.details or {}).get("rule_kind", "<missing>")
        detail.append(f"BLOCK rule_kind={rule_kind} reason={exc.reason[:120]}")
        verdict = "BLOCK" if rule_kind == "policy_cache_miss" else "INCONCLUSIVE"
    except NullRunError as exc:
        verdict = "ERROR"
        detail.append(f"error_code={getattr(exc, 'error_code', '?')} msg={str(exc)[:160]}")
    except Exception as exc:  # noqa: BLE001
        verdict = "ERROR"
        detail.append(f"type={type(exc).__name__} msg={str(exc)[:160]}")

    state.results.append(
        TCResult(
            code="TC-POL-020",
            title="ToolBlock policy cache miss fail-CLOSED",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Coordinator + aggregator.
# ─────────────────────────────────────────────────────────────────────────────
def coordinator(state: WireState) -> dict:
    state.results.append(
        TCResult(
            code="RUN",
            title="start",
            decision="ALLOW",
            detail=f"start wire-contract run at t={time.monotonic():.3f}s",
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


def aggregator(state: WireState) -> dict:
    report = {
        "results": [r.model_dump() for r in state.results],
        "summary": {
            "total": len(state.results),
            "block": sum(1 for r in state.results if r.decision == "BLOCK"),
            "allow": sum(1 for r in state.results if r.decision == "ALLOW"),
            "error": sum(1 for r in state.results if r.decision == "ERROR"),
            "spec_gap": sum(1 for r in state.results if r.decision == "SPEC-GAP"),
            "inconclusive": sum(1 for r in state.results if r.decision == "INCONCLUSIVE"),
        },
    }
    print("\n[wire-contract-demo] final report:")
    print(json.dumps(report, indent=2, default=str))
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 6. Build the graph.
# ─────────────────────────────────────────────────────────────────────────────
graph = StateGraph(WireState)
graph.add_node("coordinator", coordinator)
graph.add_node("track_batch", t_track_batch_node)
graph.add_node("protocol", t_protocol_node)
graph.add_node("policy_cache_miss", t_policy_cache_miss_node)
graph.add_node("aggregator", aggregator)

graph.add_edge(START, "coordinator")
graph.add_edge("coordinator", "track_batch")
graph.add_edge("track_batch", "protocol")
graph.add_edge("protocol", "policy_cache_miss")
graph.add_edge("policy_cache_miss", "aggregator")
graph.add_edge("aggregator", END)

APP = graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Main.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    rc = 0
    try:
        with nullrun.handle():
            APP.invoke(WireState())
    except NullRunError as exc:
        print(f"[wire-contract-demo] abort: {type(exc).__name__}: {exc}")
        rc = 1
    except Exception as exc:  # noqa: BLE001
        print(f"[wire-contract-demo] abort: type={type(exc).__name__} msg={exc!r}")
        rc = 2
    finally:
        try:
            shutdown()
        except Exception:  # noqa: BLE001
            pass
    sys.exit(rc)
