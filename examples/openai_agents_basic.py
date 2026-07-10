"""Enforce a multi-step OpenAI Agents run with @protect.

Once ``init_or_die`` runs, the OpenAI Agents SDK is auto-instrumented
(every ``Runner.run_*`` call fires ``track_llm`` events through the
httpx transport hook plus the Agents tracer). ``@protect`` adds the
*gate* (budget / kill / pause enforcement); ``@guarded`` adds
zero-boilerplate error handling for the script.

Run:
    pip install nullrun openai-agents
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/openai_agents_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from agents import Agent, Runner

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die(api_key=os.environ["NULLRUN_API_KEY"])


@guarded
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
        print(run_agent("What is the capital of France?"))
    finally:
        shutdown()