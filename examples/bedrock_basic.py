"""Enforce a Bedrock ``invoke_model`` call with ``@protect``.

NOTE: ``track_llm(...)`` below is the **boto3 escape hatch** — boto3
uses urllib3, not httpx, so the SDK's automatic transport-patch
(captured lazily on the first ``@protect`` call) cannot intercept
Bedrock calls. Fire ``track_llm`` manually once the response is
parsed.

For httpx-based SDKs (OpenAI, Anthropic, Mistral, Gemini, Cohere,
LangChain, LangGraph, OpenAI Agents, AutoGen) ``track_llm`` is
auto-fired on every successful response — do not call it manually,
that would double-count tokens.

Run:
    pip install nullrun boto3
    export NULLRUN_API_KEY=nr_live_...
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    export AWS_DEFAULT_REGION=us-east-1
    python examples/bedrock_basic.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import json
import os

import boto3

import nullrun
from nullrun import protect, shutdown, track_llm

client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))


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
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()
