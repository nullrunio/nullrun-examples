"""Enforce a raw LangChain ``ChatModel.invoke`` with @protect (no init boilerplate).

SDK 0.18.1: ``@protect`` lazy-triggers ``auto_instrument()`` on its first
call, so there is no need for an explicit ``init_or_die()``. The runtime
is created (with ``NULLRUN_API_KEY`` from the environment), ``httpx`` is
patched, and LangChain is auto-instrumented through
``patch_langchain_callback`` (BaseCallbackManager hook) AND
``patch_chat_model_invoke`` (BaseChatModel.invoke boundary).

For LangGraph's compiled-graph flow see ``langgraph_basic.py``.

What 0.18.1 gives you here:

  * zero ``init_or_die()`` boilerplate
  * zero-activity diagnostic: if ``@protect`` runs 50+ times without an
    observed ``track_llm`` event, the runtime logs a single WARNING
    naming the three most likely root causes
  * structured four-line developer report on failure
    (error_code / what / where / why / how-to-fix)

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

# 0.18.1: NO init_or_die() -- the first @protect call below
# lazily creates the runtime and auto-instruments LangChain in a
# single process-wide idempotent step. If NULLRUN_API_KEY is missing
# the runtime raises a clear NullRunConfigError at the first gate
# call -- no silent no-op.

llm = ChatOpenAI(model="gpt-4o-mini")


@protect                                  # gates each LLM call via /check; workflow is derived from api_key server-side (CLAUDE.md §12 1:1 binding)
def answer(prompt: str) -> str:
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


if __name__ == "__main__":
    try:
        # ``handle()`` catches NullRunError and prints the structured
        # developer report (error_code / what / where / why / how-to-fix)
        # to stderr before exiting 1.
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
