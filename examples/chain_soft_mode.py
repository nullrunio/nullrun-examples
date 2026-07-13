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
    pip install "nullrun[openai]" openai
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


import os

from openai import OpenAI

from nullrun import chain, guarded, init_or_die, protect, shutdown, workflow

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
        with workflow("chain-soft-mode-demo"):
            # `chain(...)` activates soft-mode pass for every /check
            # call inside the block. `op="start"` registers the chain
            # on the first call; subsequent calls auto-extend its
            # idle TTL. The chain_id is forwarded by @protect; the
            # user code never has to pass it explicitly.
            with chain("chain-soft-mode-demo-loop", op="start"):
                for i in range(50):
                    print(i, step(i))
                    # If the per-workflow budget is exhausted AND the
                    # policy is Soft, the gate now grants the call
                    # (charging it to overdraft_used). When the
                    # overdraft cap is hit, NullRunBudgetError
                    # fires -- @guarded prints the catalog message
                    # and exits.
    finally:
        shutdown()