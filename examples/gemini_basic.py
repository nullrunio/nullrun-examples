"""Smallest possible @protect usage with raw Google Gemini.

``init_or_die`` exits cleanly with the catalog message if
``NULLRUN_API_KEY`` is missing. The ``google-genai`` SDK routes
through httpx, so ``nullrun.init()`` patches the transport
automatically — every ``client.models.generate_content`` call fires
a ``track_llm`` event without any extra wiring. ``@protect`` adds
the *gate* layer (budget / kill / pause); ``@guarded`` adds
zero-boilerplate error handling.

Run:
    pip install "nullrun[gemini]" google-genai
    export NULLRUN_API_KEY=nr_live_...
    export GEMINI_API_KEY=...
    python examples/gemini_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from google import genai

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die(api_key=os.environ["NULLRUN_API_KEY"])
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


@guarded
@protect
def answer(prompt: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text or ""


if __name__ == "__main__":
    try:
        print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()