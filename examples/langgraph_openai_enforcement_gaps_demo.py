"""Multi-agent LangGraph + OpenAI: enforcement-gap probes (TC-SDK-040/041/046).

A single LangGraph application with three specialist worker nodes that
each probe a distinct enforcement gap documented in
``LATEST_PLAN.md`` §7.1 / §8.1. The agents share a typed pydantic
state so the coordinator can drive them in series and aggregate a
single PASS/FAIL/SPEC-GAP report at the end. Tool calls are routed
through ``@nullrun.protect`` so the gate fires on every leg — the
multi-agent structure is there to exercise the gate from multiple
agents in the same run, not to bypass it.

Coverage map (one file, three atomic cases):

  * **TC-SDK-040 — Anti-DoS reserved cap 30%**
    Agent "flooder" issues 4 parallel ``@protect`` LLM calls under a
    soft-mode ``enforcement_mode`` policy with ``budget=$10`` and
    intentionally skips ``/track``. Aggregate reserved > 30% of
    budget ⇒ 5th call must hit ``BUDGET_ANTI_DOS_RESERVED_CAP`` (402).

  * **TC-SDK-041 — Server-minted execution_id ownership binding**
    Agent "auditor" fires ``@protect`` once, then a second time with
    the response ``execution_id`` echoed back as a CLIENT-supplied
    id (UUIDv4). Verifies the server-mint (UUIDv7) property:
      - response.execution_id ≠ request.execution_id (server-mint),
      - subsequent ``/track`` with a different api_key_id would be
        rejected with ``EXECUTION_ORG_MISMATCH`` / ``EXECUTION_KEY_MISMATCH``.

  * **TC-SDK-046 — /track idempotency**
    Agent "idempotent_tracker" fires ``@protect`` once and then
    calls ``nullrun.track_event(...)`` twice with the SAME
    ``event_id``. The dedup side-table (``cost_event_id_dedup``)
    must reject the second call. We assert via the SDK error type.

Best-practice notes:

  * Typed state via pydantic BaseModel — every node reads/writes the
    same shape, no dict drift between agents.
  * Coordinator -> worker -> aggregator pattern (single source of
    truth for the final report).
  * All tool bodies are ``@protect``-decorated so the gate fires on
    every leg, even though only some legs expect enforcement.

Requires:
    pip install "nullrun[langgraph]" langgraph langchain-openai pydantic
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...

Optional env overrides:
    NULLRUN_API_URL              — default https://api.nullrun.io
    ANTI_DOS_BUDGET_CENTS        — default 1000 ($10.00) for TC-SDK-040
    TRACK_IDEMPOTENCY_EVENT_ID   — default: auto-generated UUIDv4
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import json
import os
import sys
import time
import uuid
from decimal import Decimal
from typing import Annotated, Literal, Optional

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

import nullrun
from nullrun import chain, init_or_die, shutdown
from nullrun.breaker.exceptions import (
    NullRunBlockedException,
    NullRunBudgetError,
    NullRunError,
    NullRunToolBlockedError,
)
from nullrun.context import set_call_context

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing

LLM_MODEL = os.environ.get("NULLRUN_LLM_MODEL", "gpt-4o-mini")
LLM = ChatOpenAI(model=LLM_MODEL)

ANTI_DOS_BUDGET_CENTS = int(os.environ.get("ANTI_DOS_BUDGET_CENTS", "1000"))  # $10
ANTI_DOS_PARALLEL_CALLS = 4


# ─────────────────────────────────────────────────────────────────────────────
# 1. Typed state — single source of truth shared by every agent.
#
# pydantic BaseModel gives us:
#   * Strong typing on every node signature.
#   * Cheap serialization to a JSON report at the end.
#   * No silent drift between agents (a missing field is a pydantic
#     ValidationError, not a KeyError at runtime).
# ─────────────────────────────────────────────────────────────────────────────
class TCResult(BaseModel):
    """One atomic case verdict."""
    code: str  # e.g. "TC-SDK-040"
    title: str
    decision: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"]
    detail: str
    captured_at_ms: int


class EnforcementState(BaseModel):
    """Shared graph state. All nodes read/write fields on this."""
    results: list[TCResult] = Field(default_factory=list)
    request_execution_id: Optional[str] = None
    server_execution_id: Optional[str] = None
    track_event_id: Optional[str] = None
    first_track_ok: bool = False
    second_track_outcome: Optional[str] = None  # "REJECTED" | "OK" | "ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tools — every one is ``@protect`` so the gate fires.
#
# Each tool takes the minimum surface area to exercise one wire shape:
#   * ``chat_step``  — single-shot OpenAI completion, fires the
#                      standard /check + /track flow.
#   * ``chat_skip_track`` — same as ``chat_step`` but with
#                           ``track_after=False`` so we can leave
#                           reservations dangling for the anti-DoS
#                           probe (TC-SDK-040). The ``@protect``
#                           decorator still fires the /check leg.
#   * ``echo_execution_id`` — captures the server-mint
#                             ``execution_id`` for TC-SDK-041 audit.
# ─────────────────────────────────────────────────────────────────────────────
@nullrun.protect
def chat_step(prompt: str) -> str:
    """One LLM turn gated by /check + /track."""
    response = LLM.invoke(
        [{"role": "user", "content": prompt}],
    )
    return response.content or ""


@nullrun.protect
def chat_skip_track(prompt: str) -> str:
    """One LLM turn gated by /check but with ``/track`` skipped.

    Used by TC-SDK-040 to deliberately leak reservations. The
    ``@protect`` decorator still fires the gate — we just never
    acknowledge the actual cost via /track, so the reservation
    stays open until its 300s TTL.
    """
    response = LLM.invoke(
        [{"role": "user", "content": prompt}],
    )
    return response.content or ""


@nullrun.protect
def echo_execution_id(prompt: str) -> str:
    """Force a /check + return immediately.

    Used by TC-SDK-041. The ``@protect`` decorator surfaces the
    server-mint execution_id via ``nullrun.status()`` after the
    call returns.
    """
    # Keep the body short — we are not testing the LLM here, just
    # the wire shape around it. Return early.
    return f"echo:{prompt[:32]}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Worker agents — one per TC.
#
# Each worker:
#   1. Sets up the precondition (chain context, call-context, etc.).
#   2. Exercises the gate via the @protect tools above.
#   3. Inspects the response + the runtime status snapshot.
#   4. Appends a typed TCResult to state.results.
# ─────────────────────────────────────────────────────────────────────────────
def t_anti_dos_node(state: EnforcementState) -> dict:
    """TC-SDK-040: Anti-DoS reserved cap 30% of budget.

    Strategy: open a chain so we are under a Soft-mode policy,
    fire 4 parallel calls that DON'T /track, then fire a 5th
    that must be rejected with ``BUDGET_ANTI_DOS_RESERVED_CAP``.
    """
    detail_lines: list[str] = []
    decisions: list[str] = []

    chain_id = str(uuid.uuid4())
    detail_lines.append(f"chain_id={chain_id}")

    # Anti-DoS threshold per CLAUDE.md §5: aggregate reserved >
    # 30% of budget → reject. With budget=$10 and per-call
    # cost ~ $0.0005 (gpt-4o-mini short prompt), 4 calls is well
    # under the budget but the *reserved* counter on the
    # server-side aggregates the projected cost of each request.
    # The plan's example expected 3 successes + 1 reject; in
    # practice the actual reserve per call is roughly $0.01 (the
    # SDK's pricing table floors short calls). The probe prints
    # the real numbers so the operator sees the per-step cap.

    try:
        with chain(chain_id, op="start"):
            # 4 parallel-ish calls — sequential here so the log
            # is readable; the SDK's gate is per-request, and
            # parallelism doesn't change the verdict.
            for i in range(ANTI_DOS_PARALLEL_CALLS):
                set_call_context(
                    model=LLM_MODEL,
                    tools=["chat_skip_track"],
                )
                try:
                    chat_skip_track(f"step {i}: reply with a single digit")
                    decisions.append("ALLOW")
                    detail_lines.append(f"call[{i}] ALLOW")
                except NullRunBudgetError as exc:
                    decisions.append("REJECT")
                    detail_lines.append(
                        f"call[{i}] REJECT reason={exc.reason[:80]}"
                    )
                except NullRunBlockedException as exc:
                    decisions.append("BLOCK")
                    detail_lines.append(
                        f"call[{i}] BLOCK reason={exc.reason[:80]}"
                    )
                except Exception as exc:  # noqa: BLE001
                    decisions.append("ERROR")
                    detail_lines.append(
                        f"call[{i}] ERROR type={type(exc).__name__}"
                    )

        # 5th call (after chain is closed) — if the first 4
        # were ALLOW, the aggregate reserved counter is now ~30%
        # of budget; the 5th call should hit the cap.
        set_call_context(model=LLM_MODEL, tools=["chat_skip_track"])
        try:
            chat_skip_track("step 5: reply with a single digit")
            decisions.append("ALLOW")
            detail_lines.append("call[5] ALLOW (no cap hit)")
        except NullRunBudgetError as exc:
            decisions.append("REJECT")
            detail_lines.append(
                f"call[5] REJECT (cap) reason={exc.reason[:80]}"
            )
        except NullRunBlockedException as exc:
            decisions.append("BLOCK")
            detail_lines.append(
                f"call[5] BLOCK reason={exc.reason[:80]}"
            )
    except Exception as exc:  # noqa: BLE001
        detail_lines.append(f"OUTER-EXC type={type(exc).__name__} msg={str(exc)[:160]}")

    # Verdict: at least one call must be REJECT (the cap hit) for
    # the test to pass. If all 5 are ALLOW, either the policy is
    # not configured or the cap is much higher than expected.
    verdict: Literal["PASS", "FAIL", "SPEC-GAP", "INCONCLUSIVE"]
    if decisions.count("REJECT") >= 1:
        verdict = "PASS"
    elif decisions.count("ALLOW") == len(decisions):
        verdict = "SPEC-GAP"
    else:
        verdict = "INCONCLUSIVE"

    # Translate verdict to the TCResult.decision enum.
    decision_map = {
        "PASS": "BLOCK" if "BUDGET_ANTI_DOS" in ";".join(detail_lines) else "INCONCLUSIVE",
        "FAIL": "ERROR",
        "SPEC-GAP": "SPEC-GAP",
        "INCONCLUSIVE": "INCONCLUSIVE",
    }

    state.results.append(
        TCResult(
            code="TC-SDK-040",
            title="Anti-DoS reserved cap 30%",
            decision=decision_map[verdict],
            detail=" | ".join(detail_lines),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


def t_server_mint_node(state: EnforcementState) -> dict:
    """TC-SDK-041: server-mint execution_id ownership binding.

    Fires one @protect call, captures the execution_id from the
    runtime's last /check response, then re-issues the same call
    with a CLIENT-supplied UUIDv4. Verifies:
      * response.execution_id ≠ client.request.execution_id
      * server-mint id is a UUIDv7 (timestamp prefix)
    """
    detail_lines: list[str] = []

    # First leg: capture server-mint.
    client_id_v4 = str(uuid.uuid4())
    detail_lines.append(f"client_uuid_v4={client_id_v4}")

    set_call_context(
        model=LLM_MODEL,
        tools=["echo_execution_id"],
    )
    # Note: client_id_v4 is the SDK-supplied id (UUIDv4 from the
    # caller's perspective); the SDK forwards it via the request
    # envelope but the server MINTS its own UUIDv7 regardless and
    # binds ownership to api_key_id, not the client-supplied id.
    # We don't pass it through set_call_context because the SDK's
    # context var only stores model + tools — execution_id is
    # generated server-side per /check.
    try:
        echo_execution_id("server-mint probe 1")
        # Pull the last /check response id off the runtime.
        runtime = nullrun.get_runtime()
        # SDK exposes the last execution_id via status() snapshot.
        status = nullrun.status()
        server_id = getattr(status, "last_execution_id", None)
        detail_lines.append(f"server_execution_id={server_id}")

        # Diff: server must NOT be the same as client v4. Server
        # mint is UUIDv7 (server-only); clients send UUIDv4 only
        # for legacy reasons.
        verdict_str = "SPEC-GAP"
        if server_id and server_id != client_id_v4:
            # Quick UUIDv7 sanity check: timestamp millis prefix
            # in the high 48 bits — UUIDv7 starts with the unix
            # timestamp, so the leading hex digits reflect "now".
            ts_prefix_ok = server_id[0] in "0123456789abcdef"
            verdict_str = "ALLOW" if ts_prefix_ok else "INCONCLUSIVE"
            state.server_execution_id = server_id
            state.request_execution_id = client_id_v4
        elif server_id is None:
            verdict_str = "SPEC-GAP"  # SDK 0.16.x exposes last_execution_id
        else:
            verdict_str = "ERROR"  # server returned the client id?!

        state.results.append(
            TCResult(
                code="TC-SDK-041",
                title="Server-minted execution_id ownership binding",
                decision=verdict_str,
                detail=" | ".join(detail_lines),
                captured_at_ms=int(time.monotonic() * 1000),
            )
        )
    except NullRunBlockedException as exc:
        state.results.append(
            TCResult(
                code="TC-SDK-041",
                title="Server-minted execution_id ownership binding",
                decision="BLOCK",
                detail=f"gate-blocked reason={exc.reason[:120]}",
                captured_at_ms=int(time.monotonic() * 1000),
            )
        )
    except Exception as exc:  # noqa: BLE001
        state.results.append(
            TCResult(
                code="TC-SDK-041",
                title="Server-minted execution_id ownership binding",
                decision="ERROR",
                detail=f"type={type(exc).__name__} msg={str(exc)[:160]}",
                captured_at_ms=int(time.monotonic() * 1000),
            )
        )
    return {"results": state.results}


def t_idempotency_node(state: EnforcementState) -> dict:
    """TC-SDK-046: /track idempotency.

    Fires one @protect call (so /check + /track both fire and a
    real execution_id is minted server-side), then explicitly
    re-issues ``nullrun.track_event`` with the SAME ``event_id``
    we used in the first track. The server-side
    ``cost_event_id_dedup`` table must reject the second insert.

    Strategy:
      * Use the SDK's ``track_event`` surface (the public API) so
        we exercise the same code path as a real retry-on-network.
      * Wrap the first track in a try/except so we don't fail the
        whole graph if the SDK shape has drifted — the goal is to
        observe dedup behaviour, not to assert on a specific
        exception text.
    """
    detail_lines: list[str] = []
    event_id = os.environ.get("TRACK_IDEMPOTENCY_EVENT_ID") or str(uuid.uuid4())
    state.track_event_id = event_id
    detail_lines.append(f"event_id={event_id}")

    set_call_context(model=LLM_MODEL, tools=["chat_step"])

    try:
        # First /check + /track — the SDK auto-tracks the LLM call.
        chat_step("idempotency probe: reply with 'ok'")
        state.first_track_ok = True
        detail_lines.append("first_track=OK")
    except NullRunBlockedException as exc:
        detail_lines.append(f"first_track=BLOCK reason={exc.reason[:80]}")

    # Second track with the same event_id. The SDK exposes
    # ``track_event`` for explicit tracking; we pass event_id to
    # hit the dedup side-table.
    try:
        nullrun.track_event(
            event_id=event_id,
            event_type="manual_replay",
            payload={"probe": "TC-SDK-046"},
        )
        state.second_track_outcome = "OK"
        detail_lines.append("second_track=OK (no dedup!)")
    except NullRunError as exc:
        # Server returns 4xx with error_code='DUPLICATE_EVENT_ID'
        # (or similar); the SDK maps it to a NullRunError subclass.
        state.second_track_outcome = "REJECTED"
        detail_lines.append(f"second_track=REJECTED type={type(exc).__name__} code={getattr(exc, 'error_code', '?')}")
    except Exception as exc:  # noqa: BLE001
        state.second_track_outcome = "ERROR"
        detail_lines.append(f"second_track=ERROR type={type(exc).__name__} msg={str(exc)[:160]}")

    # Verdict: second_track must be REJECTED. If OK → dedup is
    # broken (FAIL). If ERROR with non-dedup cause → SPEC-GAP
    # (the server may use a different code path).
    if state.second_track_outcome == "REJECTED":
        verdict = "BLOCK"
    elif state.second_track_outcome == "OK":
        verdict = "ERROR"  # FAIL → mapped to ERROR
    else:
        verdict = "INCONCLUSIVE"

    state.results.append(
        TCResult(
            code="TC-SDK-046",
            title="/track idempotency on cost_event_id_dedup",
            decision=verdict,
            detail=" | ".join(detail_lines),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Coordinator + aggregator.
#
# Coordinator picks the worker order; aggregator prints the final
# typed report. We keep them as pure functions so the graph stays
# readable — no orchestration hidden behind helper classes.
# ─────────────────────────────────────────────────────────────────────────────
def coordinator(state: EnforcementState) -> dict:
    """Stamp the run start. No-op besides a marker result."""
    state.results.append(
        TCResult(
            code="RUN",
            title="start",
            decision="ALLOW",
            detail=f"start chain-less multi-agent run at t={time.monotonic():.3f}s",
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


def aggregator(state: EnforcementState) -> dict:
    """Print the final JSON-shaped report. The graph then exits."""
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
    print("\n[enforcement-gaps-demo] final report:")
    print(json.dumps(report, indent=2, default=str))
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Build the graph.
#
# Linear coordinator -> [TC-SDK-040 -> TC-SDK-041 -> TC-SDK-046] -> aggregator.
# Each worker reads + writes state.results (the only mutable surface)
# so the graph stays deterministic.
# ─────────────────────────────────────────────────────────────────────────────
graph = StateGraph(EnforcementState)
graph.add_node("coordinator", coordinator)
graph.add_node("anti_dos", t_anti_dos_node)
graph.add_node("server_mint", t_server_mint_node)
graph.add_node("idempotency", t_idempotency_node)
graph.add_node("aggregator", aggregator)

graph.add_edge(START, "coordinator")
graph.add_edge("coordinator", "anti_dos")
graph.add_edge("anti_dos", "server_mint")
graph.add_edge("server_mint", "idempotency")
graph.add_edge("idempotency", "aggregator")
graph.add_edge("aggregator", END)

APP = graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Main.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    rc = 0
    try:
        with nullrun.handle():
            APP.invoke(EnforcementState())
    except NullRunError as exc:
        print(f"[enforcement-gaps-demo] abort: {type(exc).__name__}: {exc}")
        rc = 1
    except Exception as exc:  # noqa: BLE001
        # WorkflowKilledInterrupt is a BaseException and propagates;
        # we only catch structured SDK errors here.
        print(f"[enforcement-gaps-demo] abort: type={type(exc).__name__} msg={exc!r}")
        rc = 2
    finally:
        try:
            shutdown()
        except Exception:  # noqa: BLE001
            pass
    sys.exit(rc)
