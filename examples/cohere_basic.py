"""Smallest possible ``@protect`` usage with raw Cohere.

The first ``@protect`` call lazily creates the runtime and patches
httpx so the Cohere Python SDK fires ``track_llm`` events
automatically. NullRun's URL-keyed extractor reads the Cohere
response body and pulls out ``prompt_tokens`` /
``completion_tokens``.

Run:
    pip install nullrun cohere
    export NULLRUN_API_KEY=nr_live_...
    export COHERE_API_KEY=...
    python examples/cohere_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

import cohere

import nullrun
from nullrun import protect, shutdown

client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])


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
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
