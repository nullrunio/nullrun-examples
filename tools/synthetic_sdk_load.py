"""Bounded SDK-shaped load against an authorized NullRun backend.

Every synthetic call uses the public SDK path: @protect sends /api/v1/gate,
then track_llm sends /api/v1/track with random token usage.
No LLM provider is imported or called.

Run from the repo root so ``examples/.env`` is in the expected location:

    python tools/synthetic_sdk_load.py --duration 30 --yes
"""
from __future__ import annotations

import argparse
import os
import random
import signal
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from nullrun import guarded, init_or_die, protect, shutdown, track_llm

# Load examples/.env via the shared loader. tools/ lives next to
# examples/, so we add the repo root to sys.path first to make
# `examples._env` importable regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from examples._env import load_env

load_env(verbose=False)

STOP = threading.Event()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=0.1, help="seconds between call launches")
    parser.add_argument("--duration", type=float, default=60.0, help="duration cap in seconds")
    parser.add_argument("--requests", type=int, default=0, help="request cap; 0 uses duration only")
    parser.add_argument("--min-tokens", type=int, default=150)
    parser.add_argument("--max-tokens", type=int, default=300)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--workers", type=int, default=20, help="maximum concurrent SDK calls")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dry-run", action="store_true", help="schedule locally without HTTP")
    parser.add_argument("--yes", action="store_true", help="skip the explicit LOAD confirmation")
    args = parser.parse_args()
    if args.interval < 0.01 or args.duration <= 0 or args.workers < 1 or args.requests < 0:
        parser.error("require interval >= 0.01, duration > 0, workers >= 1, requests >= 0")
    if args.min_tokens < 0 or args.max_tokens < args.min_tokens:
        parser.error("require 0 <= min-tokens <= max-tokens")
    return args


@protect
def emit_synthetic(input_tokens: int, output_tokens: int, model: str) -> None:
    track_llm(
        input_tokens,
        output_tokens,
        model=model,
        latency_ms=0,
        metadata={"synthetic_load": True, "no_inference": True},
    )

@protect
def run_one(input_tokens: int, output_tokens: int, model: str, dry_run: bool) -> int:
    if not dry_run:
        emit_synthetic(input_tokens, output_tokens, model)
    return input_tokens + output_tokens

def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    target = "dry-run" if args.dry_run else os.getenv("NULLRUN_API_URL", "https://api.nullrun.io")
    planned = args.requests or int(args.duration / args.interval)
    planned_text = str(args.requests) if args.requests else f"about {planned} (duration-limited)"
    print(f"Target: {target}")
    print(
        f"Launch rate: {1 / args.interval:.1f} synthetic calls/s; "
        f"request cap: {planned_text}; duration cap: {args.duration:.1f}s"
    )
    print(f"Tokens: random {args.min_tokens}..{args.max_tokens}; model={args.model}; inference=disabled")
    print("Each call normally produces /gate + /track; SDK span events may also be batch-flushed.")
    if not args.dry_run and not args.yes and input("Type LOAD to continue: ").strip() != "LOAD":
        print("Cancelled.")
        return 2

    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    if not args.dry_run:
        init_or_die()

    started = time.monotonic()
    next_tick = started
    futures = []
    try:
        with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="nullrun-load") as pool:
            while not STOP.is_set():
                now = time.monotonic()
                if now - started >= args.duration or (args.requests and len(futures) >= args.requests):
                    break
                if now < next_tick:
                    STOP.wait(next_tick - now)
                    if STOP.is_set():
                        break
                total = rng.randint(args.min_tokens, args.max_tokens)
                input_tokens = rng.randint(0, total)
                futures.append(pool.submit(run_one, input_tokens, total - input_tokens, args.model, args.dry_run))
                next_tick = max(next_tick + args.interval, time.monotonic() + args.interval)

            tokens = errors = 0
            latencies = []
            for index, future in enumerate(as_completed(futures), 1):
                waited = time.monotonic()
                try:
                    tokens += future.result()
                except BaseException as exc:
                    errors += 1
                    print(f"call failed: {type(exc).__name__}: {exc}")
                latencies.append((time.monotonic() - waited) * 1000)
                if index % 50 == 0:
                    print(f"progress completed={index}/{len(futures)} exceptions={errors} tokens={tokens}")
    finally:
        if not args.dry_run:
            shutdown()

    elapsed = time.monotonic() - started
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies, default=0.0)
    print(
        f"done launched={len(futures)} exceptions={errors} tokens={tokens} elapsed={elapsed:.2f}s "
        f"launch_rate={len(futures) / elapsed if elapsed else 0:.2f}/s completion_wait_p95_ms={p95:.1f}"
    )
    print("Note: inspect stderr/backend metrics for accepted/error counts.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
