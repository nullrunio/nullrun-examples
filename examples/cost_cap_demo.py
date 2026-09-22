"""Demonstrate a hard budget cap on an agent (no init boilerplate).

The agent below loops until the per-workflow budget is exhausted. The
backend raises a 402 ``BUDGET_EXHAUSTED`` (or NR-B004 / NR-R001 wire
codes) on ``/gate``, which the SDK translates into
``NullRunBudgetError``. The 0.18.1 ``handle()`` then prints the
four-line developer report (error_code / what / where / why /
how-to-fix) so the operator immediately sees WHICH budget was
exhausted and WHICH workflow needs adjustment.

SDK 0.18.1 changes:

  * No ``init_or_die()`` -- the runtime is created lazily by the
    first ``@protect`` call. ``pip install nullrun openai`` is the
    only dependency; the ``[openai]`` extra was removed because
    NullRun never imports ``openai`` (the HTTP-level instrumentation
    covers OpenAI's responses).
  * No ``@guarded`` -- replaced with ``with nullrun.handle():`` so
    the ``NullRunBudgetError`` surfaces as the structured
    developer-facing report instead of the catalog headline
    "You've reached the usage limit for this conversation" alone.

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

# 0.18.1: NO init_or_die() -- the first @protect call below
# lazily creates the runtime and patches httpx for OpenAI's
# vendor SDK. We pass api_key="unused" so the OpenAI() constructor
# succeeds even when OPENAI_API_KEY is unset -- otherwise OpenAI's
# own constructor raises ``OpenAIError`` before we ever reach the
# gate, and the gate / budget path is never exercised. The OpenAI
# SDK never sends a real wire request with this placeholder key;
# the budget cap fires first.
client = OpenAI(api_key="placeholder-not-used-for-budget-demo")


@protect                                  # gates each LLM call via /check; workflow is derived from api_key server-side (CLAUDE.md §12 1:1 binding)
def step(i: int) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Step {i}: reply with the number. And add a random fact about this number. "}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        # ``handle()`` catches ``NullRunBudgetError`` (NR-B004 wire
        # code 402 BUDGET_EXHAUSTED) and prints the structured
        # developer report -- error_code, which workflow hit the
        # cap, which gate failed, and the user_action with the
        # dashboard URL for adjusting the budget. The loop exits
        # with code 1 the moment the budget is hit, so we don't
        # need to inspect the response.
        with nullrun.handle():
            for i in range(100):
                print(i, step(i))
    finally:
        shutdown()
