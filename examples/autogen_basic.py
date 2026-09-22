"""Enforce an AutoGen AssistantAgent run with @protect (no init boilerplate).

SDK 0.18.1: ``@protect`` lazy-triggers ``auto_instrument()`` on its first
call, so there is no need for an explicit ``init_or_die()``. The runtime
is created (with ``NULLRUN_API_KEY`` from the environment), ``httpx`` is
patched for the OpenAI client, and the AutoGen agent-runtime hook is
attached.

Run:
    pip install "nullrun[autogen]" autogen-agentchat autogen-ext-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/autogen_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

import nullrun
from nullrun import protect, shutdown

# 0.18.1: NO init_or_die() -- the first @protect call below
# lazily creates the runtime and auto-instruments autogen-agentchat.


@protect                                  # gates each LLM call via /check; workflow is derived from api_key server-side (CLAUDE.md §12 1:1 binding)
def run_agent(prompt: str) -> str:
    model_client = OpenAIChatCompletionClient(model="gpt-4o-mini")
    agent = AssistantAgent(
        name="assistant",
        model_client=model_client,
        system_message="You are a concise assistant. Answer in one sentence.",
    )
    result = asyncio.run(agent.run(task=prompt))
    # AutoGen returns a TaskResult whose messages list contains the
    # final TextMessage from the agent.
    last = result.messages[-1]
    return last.content if isinstance(last.content, str) else str(last.content)


if __name__ == "__main__":
    try:
        with nullrun.handle():
            print(run_agent("What is the capital of France?"))
    finally:
        shutdown()
