"""Advanced path: wrap a compiled LangGraph manually.

The recommended path is ``langgraph_basic.py`` — ``@protect`` lazy-
instruments LangGraph on the first call (via the ``[langgraph]``
extra's hook on ``langgraph.prebuilt.compile``), so most users never
need to touch the compiled app. Use THIS example only when the
auto-hook can't see your compiled graph — e.g. you build it inside a
worker thread or import LangGraph lazily after the first ``@protect``
call already ran.

The modern replacement for the deprecated ``nullrun.toolbox.langgraph.wrapper()``
is ``nullrun.patch_langgraph_compiled(app)`` — it returns a wrapper
that instruments the compiled graph's ``invoke`` / ``ainvoke`` /
``stream`` / ``astream`` methods without replacing the object. This
preserves ``isinstance(app, CompiledGraph)`` checks elsewhere in your
code that the old wrapper would have broken.

Run:
    pip install "nullrun[langgraph]" langgraph langchain-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/langgraph_manual_wrapper.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph

import nullrun
from nullrun import shutdown

# 0.18.1: NO init_or_die() -- the first protected call lazily
# creates the runtime and auto-instruments langgraph.

llm = ChatOpenAI(model="gpt-4o-mini")


def chat(state: MessagesState):
    return {"messages": [llm.invoke(state["messages"])]}


graph = StateGraph(MessagesState)
graph.add_node("chat", chat)
graph.add_edge("chat", END)
graph.set_entry_point("chat")
app = nullrun.patch_langgraph_compiled(graph.compile())


if __name__ == "__main__":
    try:
        with nullrun.handle():
            result = app.invoke(
                {"messages": [{"role": "user", "content": "Say hello in one word."}]},
            )
            print(result["messages"][-1].content)
    finally:
        shutdown()
