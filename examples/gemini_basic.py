"""Smallest possible ``@protect`` usage with raw Google Gemini.

The first ``@protect`` call lazily creates the runtime and patches
httpx so the ``google-genai`` SDK fires ``track_llm`` events
automatically. NullRun's URL-keyed extractor reads the Gemini
response body and pulls out token counts.

Run:
    pip install nullrun google-genai
    export NULLRUN_API_KEY=nr_live_...
    export GEMINI_API_KEY=...
    python examples/gemini_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from google import genai

import nullrun
from nullrun import protect, shutdown

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


@protect
def answer(prompt: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text or ""


if __name__ == "__main__":
    try:
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
