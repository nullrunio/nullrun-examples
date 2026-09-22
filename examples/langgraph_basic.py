"""Auto-instrument a LangGraph with ``@protect``.

The first ``@protect`` call lazy-triggers ``auto_instrument()``:
the runtime is created (with ``NULLRUN_API_KEY`` from the
environment), ``httpx`` is patched, and the LangGraph ``Pregel``
class is wrapped with ``NullRunCallback`` — all on the first
protected invocation, behind a process-wide lock so concurrent
``@protect`` calls do not double-fire.

The auto-patch is the canonical path. For tests with custom
runtimes, Pregel imported before init, or manual callback control,
see ``langgraph_manual_wrapper.py``.

If ``@protect`` runs 50+ times without an observed ``track_llm``
event, the runtime logs a single WARNING naming the three most
likely root causes (the zero-activity diagnostic).

Run:
    pip install nullrun langgraph langchain-openai
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
from nullrun import protect, shutdown

llm = ChatOpenAI(model="gpt-4o-mini")


@protect
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