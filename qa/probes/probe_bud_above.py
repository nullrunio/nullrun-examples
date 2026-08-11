"""Probe: single @protect call against workflow with Budget $0.00.
Used to verify above-threshold block. Catches the exception and prints it.
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import os
from openai import OpenAI
from nullrun import init_or_die, protect, shutdown

init_or_die()
client = OpenAI()

@protect
def call_once():
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Reply with the digit 1."}],
    )

try:
    r = call_once()
    print(f"[PROBE-RESULT] ALLOW: {r.choices[0].message.content!r}")
except Exception as e:
    print(f"[PROBE-RESULT] BLOCK: exc_type={type(e).__name__}")
    print(f"[PROBE-RESULT] msg={str(e)[:500]!r}")
    # Try to surface error_code if present
    code = getattr(e, "error_code", None) or getattr(e, "code", None)
    print(f"[PROBE-RESULT] error_code={code}")
finally:
    shutdown()