"""Enforce a multi-step OpenAI Agents run with @protect.

Once `nullrun.init()` runs, the OpenAI Agents SDK is auto-instrumented
(`instrumentation.auto.patch_openai_agents`) — every `Runner.run_*`
call already fires `track_llm` events through the httpx transport hook
plus the Agents tracer. `@protect` here adds the *gate* (budget / kill
/ pause enforcement); the cost tracking happens regardless.

Run:
    pip install nullrun openai-agents
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/openai_agents_basic.py
"""
from __future__ import annotations

import os

from agents import Agent, Runner

from nullrun import init, protect

init(api_key=os.environ["NULLRUN_API_KEY"])


@protect  # gate only — cost tracking is automatic via init()
def run_agent(prompt: str) -> str:
    agent = Agent(
        name="assistant",
        instructions="You are a concise assistant. Answer in one sentence.",
    )
    result = Runner.run_sync(agent, prompt)
    return result.final_output


if __name__ == "__main__":
    print(run_agent("What is the capital of France?"))
