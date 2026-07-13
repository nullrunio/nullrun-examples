"""Smallest possible @protect usage with raw Mistral.

``init_or_die`` exits cleanly with the catalog message if
``NULLRUN_API_KEY`` is missing. The Mistral Python SDK routes
through httpx, so ``nullrun.init()`` patches the transport
automatically — every ``client.chat.complete`` call fires a
``track_llm`` event without any extra wiring. ``@protect`` adds the
*gate* layer (budget / kill / pause); ``@guarded`` adds
zero-boilerplate error handling.

Run:
    pip install "nullrun[mistral]" mistralai
    export NULLRUN_API_KEY=nr_live_...
    export MISTRAL_API_KEY=...
    python examples/mistral_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from mistralai import Mistral

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing
client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])


@guarded
@protect
def answer(prompt: str) -> str:
    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()