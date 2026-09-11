"""Probe for RATE-H2 (v3.53) — org-aggregate rate-limit verification across TWO api_keys.

Background: v3.52 closed the Lua + Redis-side infrastructure for org-aggregate
rate limits (separate rl:tokens:org:{org_id} bucket, aggregate check FIRST so a
saturated per-key bucket can't mask org-level abuse). v3.53 closed the wire
gap: gate constructs the limiter via with_org_aggregate(...) when
KeyPolicy.org_rate_limit_per_minute is Some(n > 0). Block response emits
details.scope = "organization" | "api_key" discriminator.

This probe exercises that flow:
  - org plan = Pro (default org_rate_limit_per_minute = 100k calls/min).
  - For this probe we use a smaller per-key cap (5/min) so we can hit the
    per-key bucket quickly.
  - For the org-aggregate to fire we need to either (a) consume more than
    5 calls across both keys OR (b) have an org cap below 10 calls/min.
  - Test plan: per-key = 5/min, no org-aggregate-cap configured for this
    org. We expect: per-key1 caps at 5 ALLOW, per-key2 caps at 5 ALLOW
    (no org-aggregate because org cap is 100k). But we still verify the
    discriminator: details.scope field appears in any block.

Args (passed by runner):
  sys.argv[1] = key_1  (full nr_live_... key string)
  sys.argv[2] = key_2  (full nr_live_... key string)
  sys.argv[3] = cap    (integer, default 5)

Each runtime instance lives only long enough to drive its burst. We
construct two NullRunRuntime instances directly (not via init() singleton)
because both bursts need their own api_key and the SDK singleton can only
hold one at a time.
"""
from __future__ import annotations
import sys, pathlib
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env
load_env()

import os, time
from nullrun import shutdown
from nullrun.runtime import NullRunRuntime
from nullrun.breaker.exceptions import WorkflowKilledInterrupt

if len(sys.argv) < 4:
    print("usage: probe_rate_burst_two_keys.py <key1> <key2> <cap>")
    sys.exit(2)

KEY1 = sys.argv[1]
KEY2 = sys.argv[2]
try:
    CAP = int(sys.argv[3])
except ValueError:
    CAP = 5

API_URL = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io")
BURSTS = max(CAP + 3, 8)  # cap+3 to definitely overshoot

def burst(label: str, api_key: str) -> dict:
    """Construct a fresh runtime (NOT via singleton init) and burst."""
    print(f"\n--- BURST {label} (key prefix {api_key[:10]}...) ---")
    runtime = NullRunRuntime(
        api_key=api_key,
        api_url=API_URL,
        debug=False,
        polling=False,  # probe: skip control-plane listener
    )
    allow = 0
    block = 0
    first_block = None
    first_block_scope = None
    first_block_msg = None
    start = time.monotonic()
    try:
        for i in range(BURSTS):
            try:
                runtime.check_workflow_budget()
                allow += 1
                print(f"[{label} {i}] t={time.monotonic()-start:.3f}s allow")
            except WorkflowKilledInterrupt as exc:
                block += 1
                if first_block is None:
                    first_block = i
                    first_block_msg = str(exc)[:200]
                    # v3.53 discriminator — Scope discriminator lives on
                    # structured details. Try getattr on the structured
                    # exception if it's a typed NullRunError subclass.
                    first_block_scope = getattr(exc, "scope", None)
                print(f"[{label} {i}] t={time.monotonic()-start:.3f}s BLOCK "
                      f"code={getattr(exc,'code',None)} "
                      f"scope={getattr(exc,'scope','?')!r} "
                      f"msg={str(exc)[:120]!r}")
            except Exception as e:
                block += 1
                print(f"[{label} {i}] t={time.monotonic()-start:.3f}s OTHER-EXC "
                      f"type={type(e).__name__} msg={str(e)[:120]!r}")
    finally:
        try:
            runtime.shutdown(flush=False)
        except Exception:
            pass
    return {
        "label": label, "allow": allow, "block": block,
        "first_block": first_block, "first_block_scope": first_block_scope,
        "first_block_msg": first_block_msg,
    }

r1 = burst("KEY1", KEY1)
r2 = burst("KEY2", KEY2)

print(f"\n=== RATE-H2 SUMMARY ===")
print(f"  per_key_cap={CAP} burst_count={BURSTS}")
print(f"  KEY1: allow={r1['allow']} block={r1['block']} "
      f"first_block={r1['first_block']} scope={r1['first_block_scope']!r}")
print(f"  KEY2: allow={r2['allow']} block={r2['block']} "
      f"first_block={r2['first_block']} scope={r2['first_block_scope']!r}")

# Verdict: each key should hit per-key cap at iteration CAP
# (i.e. first_block for KEY1 == CAP, first_block for KEY2 == CAP).
# Org-aggregate firing would be visible only if org_rate_limit_per_minute
# were set below BURSTS*2 — which it is NOT for the default Pro org tier
# (100k/min). We log the discriminator to confirm v3.53 wire shape is
# live, regardless of which bucket fired.
both_first_block_correct = (
    r1["first_block"] == CAP and r2["first_block"] == CAP
)
discriminator_emitted = any(r["first_block_scope"] is not None for r in (r1, r2))
print(f"  per_key_first_block_at_cap={both_first_block_correct}")
print(f"  scope_discriminator_present={discriminator_emitted}")

verdict = "PASS" if both_first_block_correct else "UNEXPECTED"
print(f"  VERDICT: {verdict}  (RATE-H2 wire-additive details.scope={discriminator_emitted})")

try:
    shutdown()
except Exception:
    pass