"""Enforce a multi-step OpenAI Agents run with ``@protect``.

The first ``@protect`` call lazy-triggers ``auto_instrument()``:
the OpenAI Agents SDK is auto-instrumented via the ``[agents]``
extra — every ``Runner.run_*`` call fires ``track_llm`` events
through the httpx transport hook plus the Agents tracer.

``@protect`` adds the *gate* (budget / kill / pause enforcement);
``with nullrun.handle():`` catches any ``NullRunError`` and prints
the four-line developer report (error_code / what / where / why /
how-to-fix) before exiting 1.

Run:
    pip install "nullrun[agents]" openai-agents
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/openai_agents_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


from agents import Agent, Runner

import nullrun
from nullrun import protect, shutdown


@protect
def run_agent(prompt: str) -> str:
    agent = Agent(
        name="assistant",
        instructions="You are a concise assistant. Answer in one sentence.",
    )
    result = Runner.run_sync(agent, prompt)
    return result.final_output


if __name__ == "__main__":
    try:
        with nullrun.handle():
            print(run_agent("What is the capital of France?"))
    finally:
        shutdown()
