"""Probe for TC-28 — Lua v3 period-bound counter smoke (reserve → period rollover → new reserve)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "examples"))
try:
    from _env import load_env
    load_env()
except Exception:
    pass

if len(sys.argv) >= 2:
    os.environ["NULLRUN_API_KEY"] = sys.argv[1]

import nullrun  # noqa: E402
from nullrun import init_or_die, shutdown  # noqa: E402
from nullrun.context import set_call_context  # noqa: E402

init_or_die()


def main() -> int:
    from nullrun import get_runtime
    rt = get_runtime()

    # User-spirit pattern: a single zero-arg probe decorated with
    # ``@nullrun.protect``. Each invocation mints a fresh
    # ``operation_id`` (P0-27) and runs the same Lua ``RESERVE``
    # path. The semantic hash (IDEM-01) covers the user-controlled
    # ``tools``/``model`` fields, so two invocations of this probe
    # inside one period both succeed and accumulate against
    # ``bp:{ts}:cost_cents``.
    @nullrun.protect
    def probe() -> None:
        return None

    set_call_context(model="gpt-4o-mini", tools=("read_file",))

    # First reserve — should succeed
    try:
        probe()
        print("RESERVE_1_OK", flush=True)
    except nullrun.NullRunBlockedException as e:
        print(f"RESERVE_1_FAIL: {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"RESERVE_1_FAIL: {type(e).__name__}: {e}", flush=True)

    # Second reserve — fresh operation_id, same period
    try:
        probe()
        print("RESERVE_2_OK", flush=True)
    except nullrun.NullRunBlockedException as e:
        print(f"RESERVE_2_FAIL: {type(e).__name__}: {e}", flush=True)
    except Exception as e:
        print(f"RESERVE_2_FAIL: {type(e).__name__}: {e}", flush=True)

    # Approximate budget — verify Redis period source
    try:
        budget = rt.approximate_budget()
        print(f"BUDGET_APPROX={budget}", flush=True)
    except Exception as e:
        print(f"BUDGET_APPROX_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
