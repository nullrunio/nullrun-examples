"""Enforce a llama-index query with @protect.

Once ``init_or_die`` runs, ``nullrun`` auto-instruments
``llama_index.core`` through its event dispatcher — every
``LLMChatEndEvent`` and ``FunctionCallEvent`` fires a
``track_llm`` / ``track_tool`` event without any user code change.

``@protect`` adds the *gate* layer (budget / kill / pause);
``@guarded`` translates any ``NullRunError`` into a friendly exit.

Run:
    pip install "nullrun[llama-index]" llama-index-llms-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/llama_index_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from llama_index.core import Settings
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai import OpenAI

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die(api_key=os.environ["NULLRUN_API_KEY"])

Settings.llm = OpenAI(model="gpt-4o-mini")
llm = Settings.llm


@guarded
@protect
def answer(prompt: str) -> str:
    response = llm.chat([ChatMessage(role="user", content=prompt)])
    return response.message.content or ""


if __name__ == "__main__":
    try:
        print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()