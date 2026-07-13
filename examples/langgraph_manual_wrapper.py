"""Manual wrapper for a compiled LangGraph (advanced path).

When ``nullrun.init_or_die()`` auto-instrumentation is not enough —
e.g. a library re-compiles graphs after ``init()`` ran — wrap the
compiled app explicitly with ``nullrun.toolbox.langgraph.wrapper``.

For the recommended auto-instrumentation path see ``langgraph_basic.py``.

Run:
    pip install "nullrun[langgraph]" langgraph langchain-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/langgraph_manual_wrapper.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph

import nullrun
from nullrun import init_or_die, shutdown
from nullrun.toolbox.langgraph import wrapper

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing

llm = ChatOpenAI(model="gpt-4o-mini")


def chat(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}


graph = StateGraph(MessagesState)
graph.add_node("chat", chat)
graph.add_edge("chat", END)
graph.set_entry_point("chat")
app = wrapper(graph.compile())


if __name__ == "__main__":
    try:
        with nullrun.handle():
            with nullrun.workflow("langgraph-manual-wrapper-demo"):
                result = app.invoke(
                    [{"role": "user", "content": "Say hello in one word."}],
                )
                print(result["messages"][-1].content)
    finally:
        shutdown()