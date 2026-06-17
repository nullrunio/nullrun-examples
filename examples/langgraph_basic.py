"""Auto-instrument a LangGraph with `nullrun.init()`.

`nullrun.init()` attaches `NullRunCallback` automatically once `langgraph`
is importable (via `nullrun.instrumentation.auto.patch_langgraph_compiled`).
This example does not wire the callback manually — that path is discouraged
in favour of letting `init()` do it.

Run:
    pip install "nullrun[langgraph]" langgraph langchain-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/langgraph_basic.py
"""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph

from nullrun import init

init(api_key=os.environ["NULLRUN_API_KEY"])


def build_graph():
    llm = ChatOpenAI(model="gpt-4o-mini")

    def chat(state: MessagesState):
        return {"messages": [llm.invoke(state["messages"])]}

    # `StateGraph(MessagesState)` replaces the deprecated
    # `langgraph.graph.MessageGraph` (removed in langgraph 1.0).
    graph = StateGraph(MessagesState)
    graph.add_node("chat", chat)
    graph.add_edge("chat", END)
    graph.set_entry_point("chat")
    return graph.compile()


def main() -> None:
    # `init()` already attached the NullRunCallback — no manual wiring.
    graph = build_graph()
    result = graph.invoke(
        [{"role": "user", "content": "Say hello in one word."}],
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
