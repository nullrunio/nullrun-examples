"""Smallest possible ``@protect`` usage with raw Anthropic (no init boilerplate).

SDK 0.18.1:

  * No ``init_or_die()`` -- the first ``@protect`` call lazily
    creates the runtime and patches ``httpx`` so the Anthropic SDK
    (which uses httpx under the hood) fires ``track_llm`` events
    automatically. NullRun's URL-keyed extractor reads the
    Anthropic response body and pulls out ``input_tokens`` /
    ``output_tokens`` from the JSON.

  * No ``[anthropic]`` extra -- NullRun never imported the
    ``anthropic`` package; the HTTP-level instrumentation is
    vendor-agnostic. ``pip install nullrun anthropic`` is the only
    dependency, and ``anthropic`` is here because the *example*
    uses the vendor SDK, not because NullRun needs it.

  * No ``@guarded`` -- the agent uses ``with nullrun.handle():``
    instead so any SDK error surfaces as the four-line developer
    report (error_code / what / where / why / how-to-fix) instead
    of the legacy single-sentence catalog message.

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

# 0.18.1: NO init_or_die() -- the runtime is created lazily by the
# first @protect call below. If NULLRUN_API_KEY is missing the
# runtime raises NullRunConfigError at the first gate call, not a
# silent no-op.
client = Anthropic()


@protect                                  # gates each LLM call via /check; workflow is derived from api_key server-side (CLAUDE.md §12 1:1 binding)
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
        # ``handle()`` catches NullRunError and prints the structured
        # developer report (error_code / what / where / why / how-to-fix)
        # to stderr before exiting 1. The Anthropic happy path above
        # never reaches the except branch -- this is the friendly
        # error path for the misconfigured case.
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
