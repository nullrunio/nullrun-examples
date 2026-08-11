"""Demonstrate a hard budget cap on an agent.

The agent below loops until the per-workflow budget is exhausted, then
NullRun raises ``NullRunBudgetError`` (NR-B004) or
``WorkflowKilledInterrupt`` (kill via WebSocket control plane).
``@guarded`` translates the budget exception into a friendly exit; the
kill signal still propagates because it is a ``BaseException``.

Run:
    pip install nullrun openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/cost_cap_demo.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


from openai import OpenAI

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing
client = OpenAI()


@guarded
@protect
def step(i: int) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Step {i}: reply with the number."}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        for i in range(100):
            print(i, step(i))
    finally:
        shutdown()