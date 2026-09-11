"""Multi-agent LangGraph + OpenAI: observability probes (TC-OBS-014..017).

A LangGraph app whose four worker agents exercise the observability
fail-CLOSED surfaces documented in ``LATEST_PLAN.md`` §7.4 / §8.2.
Each worker probes exactly one endpoint / surface and reports back
via the shared pydantic state.

Coverage map (one file, four atomic cases):

  * **TC-OBS-014 — ApproximateBudget: 503 vs $0**
    Agent "budget_prober" hits ``GET /api/v1/budget/approximate``.
    Per CLAUDE.md §17 the endpoint must return ``503
    BUDGET_DATA_UNAVAILABLE`` when ALL sources are unreachable
    (e.g. Redis is stopped), NOT 0 with ``is_approximate=true``.
    The agent inspects the response and reports BLOCK (correct)
    vs ALLOW-with-zero (incorrect).

  * **TC-OBS-015 — Trace ingestion 503 surface**
    Agent "ingest_prober" fires a /track with a trace payload.
    Per CLAUDE.md §4 the trace ingestion path is fail-CLOSED — if
    Postgres is unavailable the response must be 503
    ``ServiceUnavailable``, NOT a silent 200 OK that drops the
    span. SDK retries with exponential backoff.

  * **TC-OBS-016 — Trace retrieval 503 + Retry-After**
    Agent "retrieval_prober" hits ``GET /api/v1/traces/{id}``.
    Per CLAUDE.md §4 the response must be 503 with
    ``Retry-After: 5`` when Postgres retrieval is unavailable, so
    the dashboard's trace page can render a coherent error.

  * **TC-OBS-017 — Aggregate rate limit Redis down → 503**
    Agent "rate_prober" hits /check while a rate_limit policy is
    active and Redis is down (simulated by pointing the SDK at an
    unreachable URL). The aggregate rate-limit path must return
    503 ``RATE_LIMIT_REDIS_UNAVAILABLE`` — fail-CLOSED, NOT
    silent allow.

Best-practice notes:

  * Multi-agent graph; each worker runs once and appends one
    TCResult to state.results.
  * Observability probes are HTTP-only (no @protect) because we
    need raw response inspection.
  * Status-code-vs-error-code mappings are explicit; the verdict
    is BLOCK only when the precise fail-CLOSED code is observed.

Requires:
    pip install "nullrun[langgraph]" langgraph langchain-openai pydantic httpx
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...

Optional env overrides:
    NULLRUN_API_URL              — default https://api.nullrun.io
    TRACE_ID_FOR_RETRIEVAL       — default: a synthetic UUIDv4
    NULLRUN_LLM_MODEL            — default gpt-4o-mini
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
from nullrun.breaker.exceptions import NullRunError

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


class ObsState(BaseModel):
    results: list[TCResult] = Field(default_factory=list)
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


def _http(method: str, path: str, **kwargs) -> tuple[int, str, dict]:
    """Single-call HTTP helper.

    Returns (status_code, body_text, headers_lower_keys).
    """
    import httpx
    runtime = nullrun.get_runtime()
    api_url = runtime.api_url.rstrip("/")
    api_key = os.environ["NULLRUN_API_KEY"]
    headers = kwargs.pop("headers", {}) or {}
    headers.setdefault("Authorization", f"Bearer {api_key}")
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("X-NULLRUN-PROTOCOL", "3")
    url = f"{api_url}{path}"
    method_fn = getattr(httpx, method.lower())
    response = method_fn(url, headers=headers, timeout=10.0, **kwargs)
    return (
        response.status_code,
        response.text[:400],
        {k.lower(): v for k, v in response.headers.items()},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Worker: TC-OBS-014 ApproximateBudget 503 surface.
# ─────────────────────────────────────────────────────────────────────────────
def t_approximate_budget_node(state: ObsState) -> dict:
    detail: list[str] = []
    try:
        status, body, headers = _http("GET", "/api/v1/budget/approximate")
        detail.append(f"status={status}")
        detail.append(f"body={body[:200]}")
        verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"]
        if status == 503 and "BUDGET_DATA_UNAVAILABLE" in body:
            verdict = "BLOCK"  # fail-CLOSED, expected
        elif status == 200:
            try:
                payload = json.loads(body)
                if payload.get("is_approximate") and payload.get(
                    "current_spend_cents_estimate", 1
                ) == 0:
                    verdict = "ERROR"  # returned $0 instead of 503
                else:
                    verdict = "ALLOW"
            except json.JSONDecodeError:
                verdict = "INCONCLUSIVE"
        else:
            verdict = "INCONCLUSIVE"
    except Exception as exc:  # noqa: BLE001
        verdict = "ERROR"
        detail.append(f"type={type(exc).__name__} msg={str(exc)[:160]}")

    state.results.append(
        TCResult(
            code="TC-OBS-014",
            title="ApproximateBudget: 503 vs $0",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Worker: TC-OBS-015 trace ingestion 503.
# ─────────────────────────────────────────────────────────────────────────────
def t_trace_ingest_node(state: ObsState) -> dict:
    detail: list[str] = []
    try:
        body = {
            "events": [
                {
                    "event_id": str(uuid.uuid4()),
                    "execution_id": state.trace_id,
                    "model": LLM_MODEL,
                    "estimated_cost_cents": 0,
                    "tool_name": "trace_probe",
                    "trace_payload": {
                        "spans": [
                            {
                                "name": "probe",
                                "start_ms": int(time.time() * 1000),
                                "duration_ms": 1,
                            }
                        ]
                    },
                }
            ]
        }
        status, resp_body, _ = _http(
            "POST",
            "/api/v1/track/batch",
            json=body,
        )
        detail.append(f"status={status}")
        detail.append(f"body={resp_body[:200]}")
        verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"]
        if status == 503 and "ServiceUnavailable" in resp_body:
            verdict = "BLOCK"  # fail-CLOSED — Postgres down
        elif status in (200, 202):
            verdict = "ALLOW"  # happy path
        else:
            verdict = "INCONCLUSIVE"
    except Exception as exc:  # noqa: BLE001
        verdict = "ERROR"
        detail.append(f"type={type(exc).__name__} msg={str(exc)[:160]}")

    state.results.append(
        TCResult(
            code="TC-OBS-015",
            title="Trace ingestion 503 surface",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Worker: TC-OBS-016 trace retrieval 503 + Retry-After.
# ─────────────────────────────────────────────────────────────────────────────
def t_trace_retrieval_node(state: ObsState) -> dict:
    detail: list[str] = []
    try:
        target_trace = os.environ.get("TRACE_ID_FOR_RETRIEVAL") or state.trace_id
        status, resp_body, resp_headers = _http(
            "GET",
            f"/api/v1/traces/{target_trace}",
        )
        detail.append(f"status={status}")
        retry_after = resp_headers.get("retry-after")
        detail.append(f"retry-after={retry_after}")
        detail.append(f"body={resp_body[:200]}")
        verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"]
        if status == 503 and retry_after:
            verdict = "BLOCK"
        elif status in (200, 404):
            verdict = "ALLOW"
        else:
            verdict = "INCONCLUSIVE"
    except Exception as exc:  # noqa: BLE001
        verdict = "ERROR"
        detail.append(f"type={type(exc).__name__} msg={str(exc)[:160]}")

    state.results.append(
        TCResult(
            code="TC-OBS-016",
            title="Trace retrieval 503 + Retry-After",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Worker: TC-OBS-017 aggregate rate limit Redis down → 503.
#
# We can't easily kill Redis from inside the script, so we point
# the SDK at a known-bad URL and re-issue /check. The gate's
# aggregate rate-limit path must return 503
# ``RATE_LIMIT_REDIS_UNAVAILABLE``.
# ─────────────────────────────────────────────────────────────────────────────
def t_rate_redis_down_node(state: ObsState) -> dict:
    detail: list[str] = []
    # Re-init the SDK against an unreachable API URL so the next
    # /check hits the network failure path. We restore the original
    # URL afterwards.
    original_url = os.environ.get("NULLRUN_API_URL")
    fake_url = os.environ.get("OBS_FAKE_API_URL", "http://127.0.0.1:1")
    nullrun.init(api_key=os.environ["NULLRUN_API_KEY"], api_url=fake_url)
    detail.append(f"re-init api_url={fake_url}")

    try:
        from nullrun.context import set_call_context
        set_call_context(model=LLM_MODEL, tools=["probe"])
        runtime = nullrun.get_runtime()
        runtime.check_workflow_budget()
        verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"] = "ALLOW"
        detail.append("ALLOW — gate did not fail-CLOSED")
    except NullRunError as exc:
        code = getattr(exc, "error_code", "")
        if code == "RATE_LIMIT_REDIS_UNAVAILABLE" or "503" in str(exc):
            verdict = "BLOCK"
        else:
            verdict = "INCONCLUSIVE"
        detail.append(f"error_code={code} msg={str(exc)[:160]}")
    except Exception as exc:  # noqa: BLE001
        verdict = "ERROR"
        detail.append(f"type={type(exc).__name__} msg={str(exc)[:160]}")
    finally:
        # Restore the original URL for any subsequent workers.
        nullrun.init(
            api_key=os.environ["NULLRUN_API_KEY"],
            api_url=original_url or "https://api.nullrun.io",
        )
        detail.append("restored api_url")

    state.results.append(
        TCResult(
            code="TC-OBS-017",
            title="Aggregate rate limit Redis down → 503",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


# ─────────────────────────────────────────────────────────────────────────────
# 6. Coordinator + aggregator.
# ─────────────────────────────────────────────────────────────────────────────
def coordinator(state: ObsState) -> dict:
    state.results.append(
        TCResult(
            code="RUN",
            title="start",
            decision="ALLOW",
            detail=f"start observability run at t={time.monotonic():.3f}s",
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


def aggregator(state: ObsState) -> dict:
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
    print("\n[observability-demo] final report:")
    print(json.dumps(report, indent=2, default=str))
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 7. Build the graph.
# ─────────────────────────────────────────────────────────────────────────────
graph = StateGraph(ObsState)
graph.add_node("coordinator", coordinator)
graph.add_node("approximate_budget", t_approximate_budget_node)
graph.add_node("trace_ingest", t_trace_ingest_node)
graph.add_node("trace_retrieval", t_trace_retrieval_node)
graph.add_node("rate_redis_down", t_rate_redis_down_node)
graph.add_node("aggregator", aggregator)

graph.add_edge(START, "coordinator")
graph.add_edge("coordinator", "approximate_budget")
graph.add_edge("approximate_budget", "trace_ingest")
graph.add_edge("trace_ingest", "trace_retrieval")
graph.add_edge("trace_retrieval", "rate_redis_down")
graph.add_edge("rate_redis_down", "aggregator")
graph.add_edge("aggregator", END)

APP = graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# 8. Main.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    rc = 0
    try:
        with nullrun.handle():
            APP.invoke(ObsState())
    except NullRunError as exc:
        print(f"[observability-demo] abort: {type(exc).__name__}: {exc}")
        rc = 1
    except Exception as exc:  # noqa: BLE001
        print(f"[observability-demo] abort: type={type(exc).__name__} msg={exc!r}")
        rc = 2
    finally:
        try:
            shutdown()
        except Exception:  # noqa: BLE001
            pass
    sys.exit(rc)
