"""Tier-1 demo probe: per-workflow rate limit (NR-R001 / NR-R002).

8 sequential /check calls (no LLM) against the per-workflow rate
limit (cap = 5 calls / minute by default). Expect:
  - Calls 0..4   : ALLOW
  - Calls 5..7   : BLOCK with NR-R001 (rate limit hit, fail-CLOSED)

Fail-CLOSED semantics: if the rate-limit Redis is unreachable the
backend returns ``RATE_LIMIT_REDIS_UNAVAILABLE`` → NR-R002 (NOT a
soft pass). This probe verifies the SDK surfaces both codes as
typed ``NullRunRateLimitRedisError`` / ``RateLimitError``.

Usage:
    python qa/probes/rate_limit_demo.py

Pre-req:
    - ``.env`` with ``NULLRUN_API_KEY`` and ``NULLRUN_API_URL``
    - Workflow under test must NOT already be saturated above the
      cap (start of a fresh minute). Otherwise you'll see blocks
      earlier than call index 5 — that's correct behaviour, not a
      bug; the probe still records first_block_i.
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import time

from nullrun import init_or_die, shutdown, get_runtime, set_call_context
from nullrun.breaker.exceptions import (
    WorkflowKilledInterrupt,
    RateLimitError,
    NullRunRateLimitRedisError,
)

init_or_die()
runtime = get_runtime()

# Provide tools context. Without this, the org-level default
# tool_block rule fires with reason="no_tools_field" and the probe
# sees WorkflowKilledInterrupt instead of the rate-limit block
# we're testing (def-nr-check-failopen-2026-09-10 follow-up).
set_call_context(tools=["read_file"])

TOTAL = 8
allow = 0
block = 0
first_block = None
first_block_t = None
allow_codes_seen = []
block_codes_seen = []
start = time.monotonic()

print(f"[RATE-LIMIT-DEMO] total={TOTAL} (expect 5 ALLOW + 3 BLOCK)", flush=True)

try:
    for i in range(TOTAL):
        try:
            runtime.check_workflow_budget()
            allow += 1
            allow_codes_seen.append("ALLOW")
            print(f"[{i}] t={time.monotonic()-start:.3f}s ALLOW", flush=True)
        except NullRunRateLimitRedisError as exc:
            # NR-R002: rate-limit Redis down. Fail-CLOSED. Surfaced
            # as a distinct typed exception so operator dashboards
            # can tell apart "limit hit" vs "limit infrastructure
            # down" — both produce user-visible 429 but operator
            # response is different (raise cap vs restore Redis).
            block += 1
            if first_block is None:
                first_block = i
                first_block_t = time.monotonic() - start
            block_codes_seen.append("NR-R002")
            print(
                f"[{i}] t={time.monotonic()-start:.3f}s BLOCK "
                f"code=NR-R002 (RATE_LIMIT_REDIS_UNAVAILABLE) "
                f"msg={str(exc)[:160]!r}",
                flush=True,
            )
        except RateLimitError as exc:
            # NR-R001: per-workflow soft rate limit hit. The base
            # ``RateLimitError`` class is the parent of any rate-
            # limit-class block; cookbook handlers should branch on
            # the typed subclasses (NR-R001 / NR-R002) when present.
            block += 1
            if first_block is None:
                first_block = i
                first_block_t = time.monotonic() - start
            code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
            block_codes_seen.append(code or "NR-R001?")
            print(
                f"[{i}] t={time.monotonic()-start:.3f}s BLOCK "
                f"type={type(exc).__name__} code={code} "
                f"msg={str(exc)[:160]!r}",
                flush=True,
            )
        except WorkflowKilledInterrupt as exc:
            # NR-W002: workflow was killed. Two possibilities:
            #   A. Server marked workflow Killed with reason
            #      "RATE_LIMIT_EXCEEDED" — this IS the rate-limit
            #      cap tripping (gate → kill state). Count as block.
            #   B. Kill from unrelated cause (operator terminate,
            #      tool_block with reason="no_tools_field" that
            #      shadowed the gate). Do NOT count.
            # Disambiguate via the embedded `reason` field.
            reason = str(exc)
            code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
            if "RATE_LIMIT_EXCEEDED" in reason:
                block += 1
                if first_block is None:
                    first_block = i
                    first_block_t = time.monotonic() - start
                block_codes_seen.append("NR-W002/RATE_LIMIT_EXCEEDED")
                print(
                    f"[{i}] t={time.monotonic()-start:.3f}s BLOCK "
                    f"code=NR-W002 (RATE_LIMIT_EXCEEDED via kill state) "
                    f"msg={str(exc)[:160]!r}",
                    flush=True,
                )
            else:
                print(
                    f"[{i}] t={time.monotonic()-start:.3f}s KILLED "
                    f"code={code} (out-of-scope — NOT rate_limit) "
                    f"msg={str(exc)[:240]!r}",
                    flush=True,
                )
                break
        except Exception as e:
            block += 1
            code = getattr(e, "error_code", None) or getattr(e, "code", None)
            block_codes_seen.append(f"OTHER:{code}")
            print(
                f"[{i}] t={time.monotonic()-start:.3f}s OTHER-EXC "
                f"type={type(e).__name__} code={code} "
                f"msg={str(e)[:160]!r}",
                flush=True,
            )
finally:
    set_call_context(tools=[])
    shutdown()

# ── Verdict ────────────────────────────────────────────────────────────
# Expected (default cap 5/min):
#   first_block_i == 5  → first 5 calls allow, 6th onward block
#   block_codes_seen contains only NR-R001 / NR-R002 (no NR-X001
#   fallback — that would mean the SDK fell back to the generic
#   "I'm unable to complete this request" block rather than the
#   typed rate-limit subclass).
VERDICT = "PASS" if first_block == 5 and all(
    c in ("NR-R001", "NR-R002", "NR-R001?", "NR-W002/RATE_LIMIT_EXCEEDED")
    for c in block_codes_seen
) else "REVIEW"
print(f"[RATE-LIMIT-DEMO] === SUMMARY ===", flush=True)
print(f"[RATE-LIMIT-DEMO] total={TOTAL} allow={allow} block={block}", flush=True)
print(f"[RATE-LIMIT-DEMO] first_block_i={first_block}", flush=True)
print(
    f"[RATE-LIMIT-DEMO] first_block_t="
    f"{(first_block_t if first_block_t is not None else float('nan')):.3f}s",
    flush=True,
)
print(f"[RATE-LIMIT-DEMO] block_codes_seen={block_codes_seen}", flush=True)
print(f"[RATE-LIMIT-DEMO] VERDICT={VERDICT}", flush=True)
