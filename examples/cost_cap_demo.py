"""Demonstrate a hard budget cap on an agent.

The agent below loops until the per-workflow budget is exhausted, then
NullRun raises `BudgetExceededError` and the loop terminates.

Run:
    pip install nullrun openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/cost_cap_demo.py
"""
from __future__ import annotations

import os

from openai import OpenAI

from nullrun import BudgetExceededError, init, protect

init(api_key=os.environ["NULLRUN_API_KEY"])
client = OpenAI()


@protect(workflow_id="cost-cap-demo")
def step(i: int) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Step {i}: reply with the number."}],
    )
    return response.choices[0].message.content or ""


def main() -> None:
    for i in range(100):
        try:
            print(i, step(i))
        except BudgetExceededError as exc:
            print(f"halted at step {i}: {exc}")
            return


if __name__ == "__main__":
    main()
