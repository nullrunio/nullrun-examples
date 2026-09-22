"""Soft-mode budget gate with an active ``chain`` context.

Soft mode (per the dashboard's per-policy ``enforcement_mode = Soft``
toggle) lets the agent keep running past its budget cap WHEN an
active chain is registered. Without a chain the same request would
hard-block with ``BUDGET_SOFT_BLOCKED``.

The ``chain`` contextmanager pushes the chain_id into a contextvar
that every ``@protect`` call picks up and forwards to the backend
as the ``chain_id`` wire field. The backend registers / extends the
chain in Redis (idle TTL 300s) and credits the projected cost to
``overdraft_used`` instead of hard-rejecting.

Run:
    pip install "nullrun" openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/chain_soft_mode.py

Requires the workflow's policy to have ``enforcement_mode = Soft``
set on the dashboard. With a Hard policy this example behaves the
same as ``cost_cap_demo.py`` -- the chain_id is forwarded but the
gate still hard-blocks when the budget is exhausted.
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


from openai import OpenAI

import nullrun
from nullrun import chain, protect, shutdown

# 0.18.1: NO init_or_die() -- the first @protect call lazily
# creates the runtime and auto-instruments openai.
client = OpenAI()


@protect
def step(i: int) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Step {i}: reply with the number."}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        with chain("chain-soft-mode-demo-loop", op="start"):
            with nullrun.handle():
                for i in range(50):
                    print(i, step(i))
    finally:
        shutdown()