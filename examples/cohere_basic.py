"""Smallest possible @protect usage with raw Cohere.

``init_or_die`` exits cleanly with the catalog message if
``NULLRUN_API_KEY`` is missing. The Cohere Python SDK routes through
httpx, so ``nullrun.init()`` patches the transport automatically —
every ``client.chat`` call fires a ``track_llm`` event without any
extra wiring. ``@protect`` adds the *gate* layer (budget / kill /
pause); ``@guarded`` adds zero-boilerplate error handling.

Run:
    pip install "nullrun[cohere]" cohere
    export NULLRUN_API_KEY=nr_live_...
    export COHERE_API_KEY=...
    python examples/cohere_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

import cohere

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die(api_key=os.environ["NULLRUN_API_KEY"])
client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])


@guarded
@protect
def answer(prompt: str) -> str:
    response = client.chat(
        model="command-r-plus",
        messages=[{"role": "user", "content": prompt}],
    )
    # Cohere returns a list of message content blocks; pick the text ones.
    parts = []
    for msg in response.message.content or []:
        text = getattr(msg, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


if __name__ == "__main__":
    try:
        print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()