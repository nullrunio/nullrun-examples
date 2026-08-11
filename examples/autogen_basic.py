from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing


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