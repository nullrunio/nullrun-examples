"""Smallest possible ``@protect`` usage with raw Mistral.

The first ``@protect`` call lazily creates the runtime and patches
httpx so the Mistral SDK fires ``track_llm`` events automatically.
NullRun's URL-keyed extractor reads the Mistral response body and
pulls out ``prompt_tokens`` / ``completion_tokens``.

Run:
    pip install nullrun mistralai
    export NULLRUN_API_KEY=nr_live_...
    export MISTRAL_API_KEY=...
    python examples/mistral_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from mistralai import Mistral

import nullrun
from nullrun import protect, shutdown

client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])


@protect
def answer(prompt: str) -> str:
    response = client.chat.complete(
        model="mistral-small-latest",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
