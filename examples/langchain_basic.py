"""Enforce a raw LangChain ``ChatModel.invoke`` with ``@protect``.

The first ``@protect`` call lazy-triggers ``auto_instrument()``:
the runtime is created (with ``NULLRUN_API_KEY`` from the
environment), ``httpx`` is patched, and LangChain is auto-
instrumented through ``patch_langchain_callback`` (callback hook)
and ``patch_chat_model_invoke`` (BaseChatModel.invoke boundary).

If ``@protect`` runs 50+ times without an observed ``track_llm``
event, the runtime logs a single WARNING naming the three most
likely root causes (the zero-activity diagnostic).

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


from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

import nullrun
from nullrun import protect, shutdown

llm = ChatOpenAI(model="gpt-4o-mini")


@protect
def answer(prompt: str) -> str:
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


if __name__ == "__main__":
    try:
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
