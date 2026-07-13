"""Smallest possible @protect usage with raw OpenAI.

``init_or_die`` exits cleanly with the catalog message if
``NULLRUN_API_KEY`` is missing. ``@guarded`` catches any
``NullRunError`` raised later. ``WorkflowKilledInterrupt`` (a
BaseException) propagates — kill must reach the top of the agent
loop.

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

from nullrun import guarded, init_or_die, protect, shutdown

init_or_die()  # reads NULLRUN_API_KEY from os.environ; friendly exit if missing
client = OpenAI()


@guarded
@protect
def answer(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()