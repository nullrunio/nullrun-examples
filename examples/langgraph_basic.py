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

from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph

import nullrun
from nullrun import init_or_die, protect, shutdown

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing

llm = ChatOpenAI(model="gpt-4o-mini")


@protect                                  # gates each LLM call via /check; workflow is derived from api_key server-side (CLAUDE.md §12 1:1 binding)
def chat(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}

graph = StateGraph(MessagesState)
graph.add_node("chat", chat)
graph.add_edge("chat", END)
graph.set_entry_point("chat")
app = graph.compile()


if __name__ == "__main__":
    try:
        with nullrun.handle():
                result = app.invoke(
                    {"messages": [{"role": "user", "content": "Say hello in one word."}]},
                )
                print(result["messages"][-1].content)
    finally:
        shutdown()