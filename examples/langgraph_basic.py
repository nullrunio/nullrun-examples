"""Auto-instrument a LangGraph with ``@nullrun.protect`` (zero-init UX).

SDK 0.18.1: ``@protect`` lazy-triggers ``auto_instrument()`` on its first
call, so there is no need for an explicit ``init_or_die()``. The runtime
is created (with ``NULLRUN_API_KEY`` from the environment), ``httpx`` is
patched, and the LangGraph ``Pregel`` class is wrapped with
``NullRunCallback`` -- all on the first protected invocation, behind a
process-wide lock so concurrent ``@protect`` calls do not double-fire.

The LangGraph callback injection in this example is the SAME one the
deprecated ``nullrun.toolbox.langgraph.wrapper(graph)`` used to perform
manually (``patch_langgraph_compiled`` in ``nullrun.instrumentation.auto``).
The auto-patch is the canonical path; ``wrapper()`` is now an escape
hatch for tests with custom runtimes, Pregel imported before init, or
manual callback control. See ``langgraph_manual_wrapper.py`` for the
explicit form.

What 0.18.1 gives you here:

  * zero ``init_or_die()`` boilerplate
  * zero framework-extras boilerplate (``pip install nullrun`` is enough
    for the HTTP-level path; ``langgraph`` is installed here only because
    the *example* uses a LangGraph agent -- NullRun's auto-patch subscribes
    to ``langgraph.pregel.Pregel`` once it's importable)
  * zero-activity diagnostic: if ``@protect`` runs 50+ times without an
    observed ``track_llm`` event, the runtime logs a single WARNING
    naming the three most likely root causes

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

# 0.18.1: NO init_or_die() here. The first @protect call below
# lazily creates the runtime and auto-instruments LangGraph in a
# single process-wide idempotent step. If NULLRUN_API_KEY is missing
# the runtime raises a clear NullRunConfigError at the first gate
# call -- no silent no-op.

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