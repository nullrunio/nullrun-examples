"""Smallest possible @protect usage with raw OpenAI (no init boilerplate).

SDK 0.18.1:

  * No ``init_or_die()`` -- the first ``@protect`` call lazily
    creates the runtime and patches httpx so the OpenAI SDK fires
    ``track_llm`` events automatically. NullRun's URL-keyed
    extractor reads the OpenAI response body and pulls out
    ``prompt_tokens`` / ``completion_tokens`` from the JSON.

  * No ``[openai]`` extra -- NullRun never imported the ``openai``
    package; the HTTP-level instrumentation is vendor-agnostic.
    ``pip install nullrun openai`` is the only dependency.

  * No ``@guarded`` -- the agent uses ``with nullrun.handle():``
    instead so any SDK error surfaces as the four-line developer
    report (error_code / what / where / why / how-to-fix) instead
    of the legacy single-sentence catalog message.

Run:
    pip install nullrun openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/raw_openai_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

from openai import OpenAI

import nullrun
from nullrun import protect, shutdown

# 0.18.1: NO init_or_die() -- the first @protect call below
# lazily creates the runtime. If NULLRUN_API_KEY is missing the
# runtime raises NullRunConfigError at the first gate call.
client = OpenAI()


@protect                                  # gates each LLM call via /check; workflow is derived from api_key server-side (CLAUDE.md §12 1:1 binding)
def answer(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        # ``handle()`` catches NullRunError and prints the structured
        # developer report (error_code / what / where / why / how-to-fix)
        # to stderr before exiting 1.
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
