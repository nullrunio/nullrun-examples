"""Demonstrate a hard budget cap on an agent.

The agent below loops until the per-workflow budget is exhausted. The
backend raises a 402 ``BUDGET_EXHAUSTED`` (or NR-B004 / NR-R001 wire
codes) on ``/gate``, which the SDK translates into
``NullRunBudgetError``. ``handle()`` prints the four-line developer
report (error_code / what / where / why / how-to-fix) so the operator
immediately sees which budget was exhausted and which workflow needs
adjustment.

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

import nullrun
from nullrun import protect, shutdown

# Pass api_key="placeholder" so the OpenAI() constructor succeeds even
# when OPENAI_API_KEY is unset — otherwise OpenAI's own constructor
# raises ``OpenAIError`` before the gate is ever reached, and the
# budget path is never exercised. The OpenAI SDK never sends a real
# wire request with this placeholder key; the budget cap fires first.
client = OpenAI(api_key="placeholder-not-used-for-budget-demo")


@protect
def step(i: int) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Step {i}: reply with the number. And add a random fact about this number. "}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        # ``handle()`` catches ``NullRunBudgetError`` (NR-B004 wire code
        # 402 BUDGET_EXHAUSTED) and prints the structured developer
        # report — error_code, which workflow hit the cap, which gate
        # failed, and the user_action with the dashboard URL for
        # adjusting the budget. The loop exits the moment the budget
        # is hit, so the response is never inspected.
        with nullrun.handle():
            for i in range(100):
                print(i, step(i))
    finally:
        shutdown()
