"""Enforce a Bedrock InvokeModel call with @protect.

``boto3`` does NOT route through httpx — it uses its own urllib3
session — so ``nullrun.init()`` cannot auto-track Bedrock calls the
way it does OpenAI / Anthropic / Mistral. We call ``track_llm``
manually with the token counts Bedrock returns in its response.

``@protect`` still gates the call (budget / kill / pause); ``@guarded``
still translates a ``NullRunError`` into a friendly exit.

Run:
    pip install "nullrun[bedrock]" boto3
    export NULLRUN_API_KEY=nr_live_...
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    export AWS_DEFAULT_REGION=us-east-1
    python examples/bedrock_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import os

import boto3

from nullrun import guarded, init_or_die, protect, shutdown, track_llm

init_or_die(api_key=os.environ["NULLRUN_API_KEY"])
client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))


@guarded
@protect
def answer(prompt: str) -> str:
    response = client.invoke_model(
        modelId="anthropic.claude-3-5-sonnet-20240620-v1:0",
        contentType="application/json",
        accept="application/json",
        body=(
            b'{"anthropic_version":"bedrock-2023-05-31",'
            b'"max_tokens":256,'
            b'"messages":[{"role":"user","content":"' + prompt.encode("utf-8") + b'"}]}'
        ),
    )
    # Parse the Anthropic-on-Bedrock response shape.
    import json

    payload = json.loads(response["body"].read())
    usage = payload.get("usage") or {}
    in_tok = int(usage.get("input_tokens") or 0)
    out_tok = int(usage.get("output_tokens") or 0)
    track_llm(input_tokens=in_tok, output_tokens=out_tok, model="claude-3-5-sonnet-bedrock")
    parts = [
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ]
    return "".join(parts)


if __name__ == "__main__":
    try:
        print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()