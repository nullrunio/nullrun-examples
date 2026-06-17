"""Demonstrate a hard budget cap on an agent.

The agent below loops until the per-workflow budget is exhausted, then
NullRun raises `NullRunBlockedException` (the gate-level budget signal) or
`WorkflowKilledInterrupt` (if a kill arrives over the WebSocket control
plane) and the loop terminates.

Run:
    pip install nullrun openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/cost_cap_demo.py
"""
from __future__ import annotations

import os

from openai import OpenAI

import nullrun
from nullrun import WorkflowKilledInterrupt, init, protect

# NullRunBlockedException lives in `nullrun.breaker.exceptions` — the
# `nullrun.breaker` package re-exports only BreakerError, BreakerTransportError,
# CostLimitExceeded, ApprovalRequired, BreakerTimeout, CircuitBreaker, CBState,
# so `from nullrun.breaker import NullRunBlockedException` would raise
# ImportError. We import the class directly from the exceptions module.
from nullrun.breaker.exceptions import NullRunBlockedException

init(api_key=os.environ["NULLRUN_API_KEY"])
client = OpenAI()


@protect
def step(i: int) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Step {i}: reply with the number."}],
    )
    return response.choices[0].message.content or ""


def main() -> None:
    # `nullrun.workflow(...)` sets a contextvar the gate reads as the
    # workflow_id. `@protect` itself takes no kwargs.
    with nullrun.workflow("cost-cap-demo"):
        for i in range(100):
            try:
                print(i, step(i))
            # `WorkflowKilledInterrupt` is a BaseException subclass (per
            # the kill contract) — catch it explicitly *before* the
            # regular Exception handler below.
            except WorkflowKilledInterrupt as exc:
                print(f"workflow killed at step {i}: {exc}")
                return
            except NullRunBlockedException as exc:
                print(f"budget exhausted at step {i}: {exc}")
                return


if __name__ == "__main__":
    main()
