"""Probe: sequential @protect calls to verify rate-limit block.
Used for RATE flow verification (no @guarded — we want to see exceptions).
Counts allow/block per iteration.
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import os, time
from openai import OpenAI
from nullrun import init_or_die, protect, shutdown

init_or_die()
client = OpenAI()

@protect
def call_once(prompt: str):
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

total = 30
allow = 0
block = 0
first_block = None
first_block_t = None
start = time.monotonic()

try:
    for i in range(total):
        try:
            r = call_once(f"Step {i}: reply with the number {i}.")
            allow += 1
            print(f"[{i:02d}] t={time.monotonic()-start:.3f}s allow")
        except Exception as e:
            block += 1
            if first_block is None:
                first_block = i
                first_block_t = time.monotonic() - start
            code = getattr(e, "error_code", None) or getattr(e, "code", None)
            print(f"[{i:02d}] t={time.monotonic()-start:.3f}s BLOCK type={type(e).__name__} code={code} msg={str(e)[:160]!r}")
finally:
    shutdown()

print(f"=== SUMMARY ===")
print(f"  total={total} allow={allow} block={block} error=0")
print(f"  first_block_i={first_block} first_block_t={(first_block_t if first_block_t is not None else float('nan')):.3f}s")