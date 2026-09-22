"""Smallest possible ``@protect`` usage with raw Anthropic.

The first ``@protect`` call lazily creates the runtime and patches
httpx so the Anthropic SDK fires ``track_llm`` events automatically.
NullRun's URL-keyed extractor reads the Anthropic response body and
pulls out ``input_tokens`` / ``output_tokens``.

Run:
    pip install nullrun anthropic
    export NULLRUN_API_KEY=nr_live_...
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/anthropic_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


from anthropic import Anthropic

import nullrun
from nullrun import protect, shutdown

client = Anthropic()


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
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
