"""Enforce an AutoGen ``BaseChatAgent.on_messages`` run with @protect.

AutoGen ships its own LLM client (``OpenAIChatCompletionClient``)
which may or may not route through httpx depending on the version
and the chat model. ``nullrun`` patches ``BaseChatAgent.on_messages``
so the agent lifecycle itself is tracked regardless of which LLM
client is underneath, and also wraps the OpenAI-compat client's
``create`` method for streaming-safe token capture.

``@protect`` adds the *gate* layer (budget / kill / pause);
``@guarded`` translates any ``NullRunError`` into a friendly exit.

Run:
    pip install "nullrun[autogen]" autogen-agentchat autogen-ext
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/autogen_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import asyncio
import os

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die(api_key=os.environ["NULLRUN_API_KEY"])


@guarded
@protect
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
        print(run_agent("What is the capital of France?"))
    finally:
        shutdown()