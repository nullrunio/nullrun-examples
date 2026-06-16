"""Enforce a LangGraph with NullRunCallback.

Run:
    pip install nullrun[langgraph] langgraph langchain-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/langgraph_basic.py
"""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessageGraph

from nullrun import init
from nullrun.instrumentation.langgraph import NullRunCallback

init(api_key=os.environ["NULLRUN_API_KEY"])


def build_graph():
    llm = ChatOpenAI(model="gpt-4o-mini")

    def chat(state):
        return {"messages": [llm.invoke(state["messages"])]}

    graph = MessageGraph()
    graph.add_node("chat", chat)
    graph.add_edge("chat", END)
    graph.set_entry_point("chat")
    return graph.compile()


def main() -> None:
    graph = build_graph()
    callback = NullRunCallback()
    result = graph.invoke(
        [{"role": "user", "content": "Say hello in one word."}],
        config={"callbacks": [callback]},
    )
    print(result[-1].content)


if __name__ == "__main__":
    main()
