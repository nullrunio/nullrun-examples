"""Smallest possible @protect usage with raw OpenAI.

Run:
    pip install nullrun openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/raw_openai_basic.py
"""
from __future__ import annotations

import os

from openai import OpenAI

from nullrun import init, protect

init(api_key=os.environ["NULLRUN_API_KEY"])
client = OpenAI()


@protect
def answer(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    print(answer("In one sentence, what does NullRun do?"))
