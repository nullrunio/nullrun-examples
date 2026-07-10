"""Enforce a raw LangChain ``ChatModel.invoke`` with @protect.

Once ``init_or_die`` runs, ``nullrun`` auto-instruments LangChain
through ``patch_langchain_callback`` (the BaseCallbackManager hook)
AND ``patch_chat_model_invoke`` (the BaseChatModel.invoke boundary).
A ``NullRunCallback`` is attached automatically — every
``llm.invoke(...)`` call fires a ``track_llm`` event.

For LangGraph's compiled-graph flow see ``langgraph_basic.py``.

Run:
    pip install "nullrun[langchain]" langchain langchain-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/langchain_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die(api_key=os.environ["NULLRUN_API_KEY"])

llm = ChatOpenAI(model="gpt-4o-mini")


@guarded
@protect
def answer(prompt: str) -> str:
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


if __name__ == "__main__":
    try:
        print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()