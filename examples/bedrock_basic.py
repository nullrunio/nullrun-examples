"""Enforce a Bedrock ``invoke_model`` call with @protect (no init boilerplate).

NOTE: ``track_llm(...)`` below is the **boto3 escape hatch** — boto3
uses urllib3, not httpx, so the SDK's automatic transport-patch
(captured lazily on the first ``@protect`` call) cannot intercept
Bedrock calls. You have to fire ``track_llm`` yourself once you have
parsed the response.

For httpx-based SDKs (OpenAI, Anthropic, Mistral, Gemini, Cohere,
LangChain, LangGraph, OpenAI Agents, AutoGen) ``track_llm`` is
auto-fired by the SDK on every successful response — you do NOT
need to call it manually and shouldn't.

SDK 0.18.1:

  * No ``init_or_die()`` -- the first ``@protect`` call lazily
    creates the runtime. There is no httpx patch to attach for
    Bedrock, but the runtime + gate path are still required.

  * No ``[bedrock]`` extra -- the URL-keyed httpx extractor for
    ``bedrock-runtime.amazonaws.com`` is shipped in the core
    package; no extra is needed for the httpx-shaped Bedrock SDK
    variants.

  * No ``@guarded`` -- the agent uses ``with nullrun.handle():``
    so any SDK error surfaces as the four-line developer report.

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

# 0.18.1: NO init_or_die() -- the first @protect call below
# lazily creates the runtime. If NULLRUN_API_KEY is missing the
# runtime raises NullRunConfigError at the first gate call.
client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))


@protect                                  # gates each LLM call via /check; workflow is derived from api_key server-side (CLAUDE.md §12 1:1 binding)
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
    # boto3 escape hatch — fire track_llm manually since the SDK cannot
    # auto-intercept urllib3 calls. Do NOT call track_llm() if you are
    # using an httpx-based SDK; that would double-count tokens.
    track_llm(input_tokens=in_tok, output_tokens=out_tok, model="claude-3-5-sonnet-bedrock")
    parts = [
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ]
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
