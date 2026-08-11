"""Minimal SDK script for PARAMS Approval Rule testing.

Calls the @sensitive @protect-wrapped `delete_user_auto` tool with the
specified force value. The PARAMS rule matches `force=true` only, so:
  - force=False → rule does NOT match → call allowed
  - force=True  → rule matches → approval required → triggers gate

Usage:
    python ar_params_run.py [force_value]
        force_value = "true" or "false" (default: "false")
"""
from __future__ import annotations

import json
import sys

import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env

load_env()

import nullrun
from nullrun import init_or_die, shutdown
from nullrun.breaker.exceptions import NullRunBlockedException
from nullrun.decorators import protect, sensitive

init_or_die()

force_str = sys.argv[1] if len(sys.argv) > 1 else "false"
force = (force_str.lower() == "true")


@sensitive
@protect
def delete_user_auto(user_id: str, force: bool) -> str:
    """Tool with @sensitive (auto-extracts all kwargs) and @protect."""
    print(f"  [delete_user_auto] user_id={user_id!r} force={force} -> OK (body ran)", flush=True)
    return json.dumps({"status": "ok", "tool": "delete_user_auto", "force": force, "user_id": user_id})


if __name__ == "__main__":
    print(f"[ar_params_run] starting, force={force}", flush=True)
    try:
        with nullrun.handle():
            try:
                result = delete_user_auto(user_id="cust-demo", force=force)
                print(f"[ar_params_run] decision=allow result={result}", flush=True)
            except NullRunBlockedException as exc:
                print(f"[ar_params_run] decision=block reason={exc.reason!r}", flush=True)
            except Exception as exc:
                print(f"[ar_params_run] decision=error type={type(exc).__name__} exc={exc!r}", flush=True)
    finally:
        shutdown()