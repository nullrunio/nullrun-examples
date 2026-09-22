"""Smallest possible @protect usage with raw Cohere (no init boilerplate).

SDK 0.18.1:

  * No ``init_or_die()`` -- the first ``@protect`` call lazily
    creates the runtime and patches httpx so the Cohere Python SDK
    (which routes through httpx) fires ``track_llm`` events
    automatically. NullRun's URL-keyed extractor reads the Cohere
    response body and pulls out ``prompt_tokens`` /
    ``completion_tokens`` from the JSON.

  * No ``[cohere]`` extra -- NullRun never imported the ``cohere``
    package; the HTTP-level instrumentation is vendor-agnostic.
    ``pip install nullrun cohere`` is the only dependency.

  * No ``@guarded`` -- the agent uses ``with nullrun.handle():``
    instead so any SDK error surfaces as the four-line developer
    report (error_code / what / where / why / how-to-fix) instead
    of the legacy single-sentence catalog message.

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

# 0.18.1: NO init_or_die() -- the first @protect call below
# lazily creates the runtime. If NULLRUN_API_KEY is missing the
# runtime raises NullRunConfigError at the first gate call.
client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])


@protect                                  # gates each LLM call via /check; workflow is derived from api_key server-side (CLAUDE.md §12 1:1 binding)
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
        # ``handle()`` catches NullRunError and prints the structured
        # developer report (error_code / what / where / why / how-to-fix)
        # to stderr before exiting 1.
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
