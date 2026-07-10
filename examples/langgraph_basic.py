"""Auto-instrument a LangGraph with ``nullrun.init_or_die()``.

``init_or_die()`` attaches ``NullRunCallback`` automatically once
``langgraph`` is importable (``nullrun.instrumentation.auto.patch_langgraph_compiled``).
For the manual path (re-compiled graphs, libraries that hide
compilation), see ``langgraph_manual_wrapper.py``.

Run:
    pip install "nullrun[langgraph]" langgraph langchain-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/langgraph_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph

import nullrun
from nullrun import init_or_die, shutdown

init_or_die(api_key=os.environ["NULLRUN_API_KEY"])

llm = ChatOpenAI(model="gpt-4o-mini")


def chat(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}


# `StateGraph(MessagesState)` replaces the deprecated
# `langgraph.graph.MessageGraph` (removed in langgraph 1.0).
graph = StateGraph(MessagesState)
graph.add_node("chat", chat)
graph.add_edge("chat", END)
graph.set_entry_point("chat")
app = graph.compile()


if __name__ == "__main__":
    # `with nullrun.handle():` catches any NullRunError raised inside
    # the graph and exits with the catalog user-message. WorkflowKilledInterrupt
    # (BaseException) propagates unchanged.
    try:
        with nullrun.handle():
            with nullrun.workflow("langgraph-basic-demo"):
                result = app.invoke(
                    [{"role": "user", "content": "Say hello in one word."}],
                )
                print(result["messages"][-1].content)
    finally:
        # Send a clean WS close frame so the backend does not log
        # "Connection reset without closing handshake". No-op if
        # init() was never called.
        shutdown()