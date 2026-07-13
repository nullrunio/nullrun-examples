"""Smallest possible @protect usage with raw Anthropic.

``init_or_die`` exits cleanly with the catalog message if
``NULLRUN_API_KEY`` is missing. The Anthropic Python SDK routes
through httpx, so ``nullrun.init()`` patches the transport
automatically — every ``client.messages.create`` call fires a
``track_llm`` event without any extra wiring. ``@protect`` adds the
*gate* layer (budget / kill / pause); ``@guarded`` adds
zero-boilerplate error handling.

Run:
    pip install "nullrun[anthropic]" anthropic
    export NULLRUN_API_KEY=nr_live_...
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/anthropic_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from anthropic import Anthropic

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing
client = Anthropic()


@guarded
@protect
def answer(prompt: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    # Anthropic returns a list of content blocks; concatenate text parts.
    return "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )


if __name__ == "__main__":
    try:
        print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()