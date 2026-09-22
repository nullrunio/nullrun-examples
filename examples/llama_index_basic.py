"""Enforce a llama-index query with ``@protect``.

The first ``@protect`` call lazy-triggers ``auto_instrument()``:
the runtime is created (with ``NULLRUN_API_KEY`` from the
environment), and llama-index is auto-instrumented through its
event dispatcher — every ``LLMChatEndEvent`` and
``FunctionCallEvent`` fires a ``track_llm`` / ``track_tool`` event
without any user code change.

``@protect`` adds the *gate* layer (budget / kill / pause);
``with nullrun.handle():`` translates any ``NullRunError`` into the
four-line developer report (error_code / what / where / why /
how-to-fix) before exiting 1.

Run:
    pip install "nullrun[llama-index]" llama-index-llms-openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/llama_index_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


from llama_index.core import Settings
from llama_index.core.llms import ChatMessage
from llama_index.llms.openai import OpenAI

import nullrun
from nullrun import protect, shutdown

_llm = OpenAI(model="gpt-4o-mini")
# llama-index reads `Settings.llm` at query-time; bind once, reference via Settings.
Settings.llm = _llm
llm = _llm


@protect
def answer(prompt: str) -> str:
    response = llm.chat([ChatMessage(role="user", content=prompt)])
    return response.message.content or ""


if __name__ == "__main__":
    try:
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
