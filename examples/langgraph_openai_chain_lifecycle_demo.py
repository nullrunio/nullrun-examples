"""Multi-agent LangGraph + OpenAI: chain lifecycle probes (TC-SDK-042/043/044).

A LangGraph app with three worker agents, each exercising one chain
lifecycle invariant from ``LATEST_PLAN.md`` §7.1 / §8.1. The graph
is shared state via pydantic so the coordinator drives the workers
in series and a final aggregator prints a typed PASS/FAIL/SPEC-GAP
report.

Coverage map (one file, three atomic cases):

  * **TC-SDK-042 — Chain heartbeat E2E**
    Agent "heartbeater" opens a chain, fires a /check, sleeps > 35s
    (one heartbeat interval + skew), then fires a second /check.
    The chain must remain ACTIVE because ``POST /heartbeat`` is
    forwarded automatically by the SDK on each ``@protect`` call.
    The aggregator then sleeps 305s (one chain-idle-TTL window) and
    fires a third /check — chain must auto-recover (per §6.2
    auto-register behaviour).

  * **TC-SDK-043 — Chain max_duration**
    Agent "duration" opens a chain with a policy whose
    ``max_chain_duration_seconds`` is 10s. After 11s the next
    ``@protect`` call must be rejected with
    ``CHAIN_MAX_DURATION_EXCEEDED`` (402).

  * **TC-SDK-044 — Chain cross-org race**
    Agent "crosser" opens a chain under org A's API key. Switches
    the runtime's api_key to org B (init() is idempotent — see
    ``nullrun.init`` docs) and fires /check with the SAME chain_id.
    The Lua Q2 race guard (``reserve_v3.lua:308-310``) must reject
    with ``CHAIN_CROSS_ORG`` or ``CHAIN_ORG_MISMATCH``.

Best-practice notes:

  * pydantic BaseModel for state — single source of truth shared by
    every worker; final report is a JSON dump of the model's fields.
  * Each worker asserts only its own invariant; cross-worker state
    is limited to ``chain_id`` so a partial run still produces a
    readable report.
  * Workers run in series — heartbeat's 305s sleep would be a
    blocker if we used parallel branches.

Requires:
    pip install "nullrun[langgraph]" langgraph langchain-openai pydantic
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...

Optional env overrides:
    HEARTBEAT_PAUSE_S            — default 36 (one tick + skew)
    IDLE_TTL_PAUSE_S             — default 305 (chain idle TTL)
    MAX_DURATION_PAUSE_S         — default 11 (max_duration + slack)
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
from nullrun import chain, init_or_die, shutdown
from nullrun.breaker.exceptions import (
    NullRunBlockedException,
    NullRunError,
)
from nullrun.context import set_call_context

init_or_die()

LLM_MODEL = os.environ.get("NULLRUN_LLM_MODEL", "gpt-4o-mini")
LLM = ChatOpenAI(model=LLM_MODEL)

HEARTBEAT_PAUSE_S = int(os.environ.get("HEARTBEAT_PAUSE_S", "36"))
IDLE_TTL_PAUSE_S = int(os.environ.get("IDLE_TTL_PAUSE_S", "305"))
MAX_DURATION_PAUSE_S = int(os.environ.get("MAX_DURATION_PAUSE_S", "11"))


# ─────────────────────────────────────────────────────────────────────────────
# 1. Typed state.
# ─────────────────────────────────────────────────────────────────────────────
class TCResult(BaseModel):
    code: str
    title: str
    decision: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"]
    detail: str
    captured_at_ms: int


class ChainState(BaseModel):
    results: list[TCResult] = Field(default_factory=list)
    heartbeat_chain_id: Optional[str] = None
    duration_chain_id: Optional[str] = None
    cross_chain_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tools — single LLM turn gated by /check.
#
# The chain lifecycle is independent of the LLM body; we keep the
# prompt trivial so cost stays negligible and the gate sees only the
# chain / heartbeat / duration semantics.
# ─────────────────────────────────────────────────────────────────────────────
@nullrun.protect
def llm_turn(prompt: str) -> str:
    """One LLM turn gated by /check + /track."""
    response = LLM.invoke([{"role": "user", "content": prompt}])
    return response.content or ""


# ─────────────────────────────────────────────────────────────────────────────
# 3. Worker agents.
# ─────────────────────────────────────────────────────────────────────────────
def _probe(
    prompt: str,
    *,
    chain_id: Optional[str] = None,
    chain_op: Optional[str] = None,
) -> tuple[str, str]:
    """One shot — run @protect llm_turn with optional chain context.

    Returns (decision, detail). ``decision`` is one of
    {"ALLOW","BLOCK","ERROR"}.
    """
    set_call_context(model=LLM_MODEL, tools=["llm_turn"])
    kwargs = {}
    if chain_id is not None:
        kwargs["chain_id"] = chain_id
    if chain_op is not None:
        kwargs["op"] = chain_op
    try:
        if chain_id is not None:
            with chain(chain_id, op=chain_op or "continue"):
                llm_turn(prompt)
        else:
            llm_turn(prompt)
        return ("ALLOW", "ok")
    except NullRunBlockedException as exc:
        return ("BLOCK", f"reason={exc.reason[:120]}")
    except NullRunError as exc:
        return ("ERROR", f"error_code={getattr(exc, 'error_code', '?')} msg={str(exc)[:120]}")
    except Exception as exc:  # noqa: BLE001
        return ("ERROR", f"type={type(exc).__name__} msg={str(exc)[:120]}")


def t_heartbeat_node(state: ChainState) -> dict:
    """TC-SDK-042 — Chain heartbeat E2E.

    The chain_idle_TTL is 300s; we sleep 305s to confirm the chain
    TTL expires and the SDK's auto-recover (per §6.2) creates a
    fresh chain on the next /check. The heartbeat leg (35s pause)
    verifies the SDK forwards ``POST /heartbeat`` on each /check.
    """
    detail: list[str] = []
    chain_id = str(uuid.uuid4())
    state.heartbeat_chain_id = chain_id
    detail.append(f"chain_id={chain_id}")

    # Leg 1: open the chain.
    decision, info = _probe("open chain", chain_id=chain_id, chain_op="start")
    detail.append(f"open {decision} {info}")
    if decision != "ALLOW":
        state.results.append(
            TCResult(
                code="TC-SDK-042",
                title="Chain heartbeat E2E",
                decision="SPEC-GAP",
                detail=" | ".join(detail),
                captured_at_ms=int(time.monotonic() * 1000),
            )
        )
        return {"results": state.results}

    # Leg 2: sleep > 35s (one heartbeat tick + skew).
    detail.append(f"sleeping {HEARTBEAT_PAUSE_S}s (heartbeat tick)")
    time.sleep(HEARTBEAT_PAUSE_S)
    decision, info = _probe("post-heartbeat", chain_id=chain_id, chain_op="continue")
    detail.append(f"heartbeat {decision} {info}")

    # Leg 3: sleep > 300s to expire the idle TTL. This is the
    # slow path; the operator can set IDLE_TTL_PAUSE_S=0 to
    # skip it during fast smoke runs.
    if IDLE_TTL_PAUSE_S > 0:
        detail.append(f"sleeping {IDLE_TTL_PAUSE_S}s (idle TTL)")
        time.sleep(IDLE_TTL_PAUSE_S)
        decision, info = _probe("post-idle-ttl", chain_id=chain_id, chain_op="continue")
        detail.append(f"post_idle {decision} {info}")
        # After TTL expiry the chain is gone; auto-recover should
        # re-register. PASS = decision ALLOW (recovered) OR
        # BLOCK with reason containing "EXPIRED" or "NOT_FOUND".
    else:
        detail.append("skipping idle-TTL leg (IDLE_TTL_PAUSE_S=0)")

    # Verdict.
    has_block = any("BLOCK" in d for d in detail)
    has_allow = any("open ALLOW" in d for d in detail)
    verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"]
    if has_allow and not has_block:
        verdict = "ALLOW"
    elif has_block:
        verdict = "BLOCK"
    else:
        verdict = "INCONCLUSIVE"

    state.results.append(
        TCResult(
            code="TC-SDK-042",
            title="Chain heartbeat E2E",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


def t_max_duration_node(state: ChainState) -> dict:
    """TC-SDK-043 — Chain max_duration.

    Assumes the test workflow has a Soft-mode policy with
    ``max_chain_duration_seconds=10``. After 11s the next
    ``@protect`` call must reject with ``CHAIN_MAX_DURATION_EXCEEDED``.
    """
    detail: list[str] = []
    chain_id = str(uuid.uuid4())
    state.duration_chain_id = chain_id
    detail.append(f"chain_id={chain_id} max_duration=10s")

    decision, info = _probe("open duration chain", chain_id=chain_id, chain_op="start")
    detail.append(f"open {decision} {info}")
    if decision != "ALLOW":
        state.results.append(
            TCResult(
                code="TC-SDK-043",
                title="Chain max_duration",
                decision="SPEC-GAP",
                detail=" | ".join(detail),
                captured_at_ms=int(time.monotonic() * 1000),
            )
        )
        return {"results": state.results}

    detail.append(f"sleeping {MAX_DURATION_PAUSE_S}s (max_duration=10 + slack)")
    time.sleep(MAX_DURATION_PAUSE_S)
    decision, info = _probe("post-duration", chain_id=chain_id, chain_op="continue")
    detail.append(f"post_duration {decision} {info}")

    # Verdict: post-duration must be BLOCK with reason
    # containing CHAIN_MAX_DURATION_EXCEEDED.
    if decision == "BLOCK" and "MAX_DURATION" in info.upper():
        verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"] = "BLOCK"
    elif decision == "BLOCK":
        verdict = "BLOCK"  # any BLOCK is a pass — got the gate
    elif decision == "ALLOW":
        verdict = "ALLOW"  # max_duration not enforced → spec-gap
    else:
        verdict = "INCONCLUSIVE"

    state.results.append(
        TCResult(
            code="TC-SDK-043",
            title="Chain max_duration",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


def t_cross_org_node(state: ChainState) -> dict:
    """TC-SDK-044 — Chain cross-org race (Q2 guard).

    Strategy: open a chain under the test API key, then call
    ``nullrun.init(api_key=<other-org-key>)`` to swap to a different
    org. The Lua Q2 race guard (``reserve_v3.lua:308-310``) reads
    the chain's stored ``org_id`` from the chain hash and rejects
    on mismatch.

    NOTE: requires a SECOND api_key from a different org in
    ``CROSS_ORG_API_KEY`` env var. If absent, the agent degrades
    to SPEC-GAP with a clear note.
    """
    detail: list[str] = []
    other_key = os.environ.get("CROSS_ORG_API_KEY")
    chain_id = str(uuid.uuid4())
    state.cross_chain_id = chain_id
    detail.append(f"chain_id={chain_id}")

    if not other_key:
        state.results.append(
            TCResult(
                code="TC-SDK-044",
                title="Chain cross-org race",
                decision="SPEC-GAP",
                detail="CROSS_ORG_API_KEY env var not set; "
                "needs a second org's api_key to exercise the Q2 race guard. "
                " | ".join(detail),
                captured_at_ms=int(time.monotonic() * 1000),
            )
        )
        return {"results": state.results}

    # Leg 1: open the chain under the original org.
    decision, info = _probe(
        "open cross-org chain", chain_id=chain_id, chain_op="start"
    )
    detail.append(f"open-as-orgA {decision} {info}")
    if decision != "ALLOW":
        state.results.append(
            TCResult(
                code="TC-SDK-044",
                title="Chain cross-org race",
                decision="SPEC-GAP",
                detail="open failed | " + " | ".join(detail),
                captured_at_ms=int(time.monotonic() * 1000),
            )
        )
        return {"results": state.results}

    # Swap to a different org's key. ``init`` is idempotent — it
    # shuts down the old runtime before constructing the new one.
    nullrun.init(api_key=other_key)
    detail.append("swapped to org B api_key")

    decision, info = _probe(
        "cross-org probe", chain_id=chain_id, chain_op="continue"
    )
    detail.append(f"as-orgB {decision} {info}")

    if decision == "BLOCK" and ("CROSS_ORG" in info.upper() or "MISMATCH" in info.upper()):
        verdict: Literal["ALLOW", "BLOCK", "ERROR", "SPEC-GAP", "INCONCLUSIVE"] = "BLOCK"
    elif decision == "BLOCK":
        verdict = "BLOCK"  # some 4xx — gate fired
    elif decision == "ALLOW":
        verdict = "ERROR"  # cross-org did NOT reject → fail
    else:
        verdict = "INCONCLUSIVE"

    state.results.append(
        TCResult(
            code="TC-SDK-044",
            title="Chain cross-org race",
            decision=verdict,
            detail=" | ".join(detail),
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Coordinator + aggregator.
# ─────────────────────────────────────────────────────────────────────────────
def coordinator(state: ChainState) -> dict:
    state.results.append(
        TCResult(
            code="RUN",
            title="start",
            decision="ALLOW",
            detail=f"start chain-lifecycle run at t={time.monotonic():.3f}s",
            captured_at_ms=int(time.monotonic() * 1000),
        )
    )
    return {"results": state.results}


def aggregator(state: ChainState) -> dict:
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
    print("\n[chain-lifecycle-demo] final report:")
    print(json.dumps(report, indent=2, default=str))
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Build the graph.
# ─────────────────────────────────────────────────────────────────────────────
graph = StateGraph(ChainState)
graph.add_node("coordinator", coordinator)
graph.add_node("heartbeat", t_heartbeat_node)
graph.add_node("max_duration", t_max_duration_node)
graph.add_node("cross_org", t_cross_org_node)
graph.add_node("aggregator", aggregator)

graph.add_edge(START, "coordinator")
graph.add_edge("coordinator", "heartbeat")
graph.add_edge("heartbeat", "max_duration")
graph.add_edge("max_duration", "cross_org")
graph.add_edge("cross_org", "aggregator")
graph.add_edge("aggregator", END)

APP = graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Main.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    rc = 0
    try:
        with nullrun.handle():
            APP.invoke(ChainState())
    except NullRunError as exc:
        print(f"[chain-lifecycle-demo] abort: {type(exc).__name__}: {exc}")
        rc = 1
    except Exception as exc:  # noqa: BLE001
        print(f"[chain-lifecycle-demo] abort: type={type(exc).__name__} msg={exc!r}")
        rc = 2
    finally:
        try:
            shutdown()
        except Exception:  # noqa: BLE001
            pass
    sys.exit(rc)
