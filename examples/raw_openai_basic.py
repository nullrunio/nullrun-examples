"""Smallest possible ``@protect`` usage with raw OpenAI.

The first ``@protect`` call lazily creates the runtime and patches
httpx so the OpenAI SDK fires ``track_llm`` events automatically.
NullRun's URL-keyed extractor reads the OpenAI response body and
pulls out ``prompt_tokens`` / ``completion_tokens``.

Run:
    pip install nullrun openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/raw_openai_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


from openai import OpenAI

import nullrun
from nullrun import protect, shutdown

client = OpenAI()


@protect
def answer(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
