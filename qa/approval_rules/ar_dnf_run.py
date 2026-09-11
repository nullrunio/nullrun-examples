"""Custom DNF Approval Rule probe (TOOLS-MATCH_3).

TOOLS-MATCH with a **Custom DNF** condition fires when EITHER disjunct
matches all of its conjuncts. DNF = Disjunctive Normal Form
(OR of ANDs).

This script wraps a 4-arg tool ``process_transaction`` and exercises
the canonical DNF rule from LATEST_PLAN §6:

    (region ∈ {EU, US}  AND credit=true)         OR
    (total ∈ [100, 500]  AND criminal=true)

Each invocation of the script triggers ONE ``process_transaction``
call with the scenario's params and prints the gate's decision. The
script does NOT orchestrate the scenarios — a shell wrapper picks
argv combinations from a matrix and the operator confirms or rejects
each one on the dashboard.

Canonical scenario matrix (matches LATEST_PLAN G2):

    region  credit  total  criminal  expected
    ──────  ──────  ─────  ────────  ────────
    EU      true    50     false     APPROVE  (group 1)
    US      true    50     false     APPROVE  (group 1)
    APAC    true    50     false     no fire  (region ∉ {EU,US})
    EU      false   50     false     no fire  (credit != true)
    APAC    false   200    true      APPROVE  (group 2)
    APAC    false   900    true      no fire  (total ∉ [100,500])
    APAC    false   200    false     no fire  (criminal != true)
    APAC    true    900    false     no fire  (neither group matches)

Usage:
    python ar_dnf_run.py [region] [credit] [total] [criminal]

Where each argument is positional:
    region   = "EU" | "US" | "APAC" | ...   (any string)
    credit   = "true" | "false"
    total    = integer, e.g. "200"
    criminal = "true" | "false"

Defaults (no argv) = group-1 positive scenario (region=EU, credit=true,
total=50, criminal=false):

    python ar_dnf_run.py

Setup on the dashboard before running (matcher syntax is the canonical
Phase 1 / MVP 1.1 ToolParameters vocabulary; confirm with backend team
if "in" / "in_range" are not surfaced in the UI):

    /control-center/policies/approval-rules
        -> New rule
        -> Workflow: <your API key's bound workflow>
        -> Tool patterns: process_transaction
        -> Typed condition: ToolParameters
        -> Custom DNF:
              group 1: param="region"   matcher="in"        value=["EU","US"]
                        param="credit"   matcher="equals"    value=true
              group 2: param="total"     matcher="in_range"  value=[100,500]
                        param="criminal" matcher="equals"    value=true
        -> Action:    require_approval
        -> Priority:  100
        -> Timeout:   300
"""
from __future__ import annotations

import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env

load_env()

import json

import nullrun
from nullrun import init_or_die, shutdown
from nullrun.breaker.exceptions import NullRunBlockedException
from nullrun.decorators import protect, sensitive
from nullrun.extractor import tool_params

init_or_die()


# 4-arg tool — each kwarg is forwarded under its own operator-facing
# param name. The wire payload (BusinessImpact.kind="tool_call") carries:
#     params={"region": ..., "credit": ..., "total": ..., "criminal": ...}
# so a Custom-DNF rule can reference any combination of those names.
@sensitive(impact=tool_params({
    "region": "region",
    "credit": "credit",
    "total": "total",
    "criminal": "criminal",
}))
@protect
def process_transaction(region: str, credit: bool, total: int, criminal: bool) -> str:
    """Tool under DNF rule — 4 typed params forwarded to the gate."""
    print(
        f"  [process_transaction] region={region!r} credit={credit} "
        f"total={total} criminal={criminal} -> OK (body ran)",
        flush=True,
    )
    return json.dumps({
        "status": "ok",
        "tool": "process_transaction",
        "region": region,
        "credit": credit,
        "total": total,
        "criminal": criminal,
    })


def _parse_bool(name: str, value: str) -> bool:
    """Strict boolean parser — rejects anything that isn't true/false."""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise SystemExit(
        f"[ar_dnf_run] bad {name}={value!r}; expected 'true' or 'false'"
    )


if __name__ == "__main__":
    # Defaults = group-1 positive scenario so a bare invocation still
    # exercises the gate (matches TC-AR-016 expected case 1 in the
    # scenario matrix above).
    region_arg   = sys.argv[1] if len(sys.argv) > 1 else "EU"
    credit_arg   = sys.argv[2] if len(sys.argv) > 2 else "true"
    total_arg    = sys.argv[3] if len(sys.argv) > 3 else "50"
    criminal_arg = sys.argv[4] if len(sys.argv) > 4 else "false"

    region = str(region_arg)
    credit = _parse_bool("credit", credit_arg)
    try:
        total = int(total_arg)
    except ValueError:
        raise SystemExit(f"[ar_dnf_run] bad total={total_arg!r}; expected integer")
    criminal = _parse_bool("criminal", criminal_arg)

    print(
        f"[ar_dnf_run] starting, region={region!r} credit={credit} "
        f"total={total} criminal={criminal}",
        flush=True,
    )

    try:
        with nullrun.handle():
            try:
                result = process_transaction(
                    region=region, credit=credit, total=total, criminal=criminal
                )
                print(f"[ar_dnf_run] decision=allow result={result}", flush=True)
            except NullRunBlockedException as exc:
                print(f"[ar_dnf_run] decision=block reason={exc.reason!r} details={exc.details!r}", flush=True)
            except Exception as exc:
                print(f"[ar_dnf_run] decision=error type={type(exc).__name__} exc={exc!r}", flush=True)
    finally:
        shutdown()