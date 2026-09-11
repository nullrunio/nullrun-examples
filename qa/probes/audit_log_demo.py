"""Probe for TC-18 — GET /audit-log list."""
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

from nullrun import init_or_die, shutdown  # noqa: E402

init_or_die()


def main() -> int:
    from nullrun import get_runtime
    rt = get_runtime()

    from nullrun.audit import AuditQuery
    try:
        result = rt.audit.list(query=AuditQuery(limit=5))
        print(f"AUDIT_LIST={result}", flush=True)
        # Inspect entries list from pydantic model or dict
        items = getattr(result, "entries", None)
        if items is None and isinstance(result, dict):
            items = result.get("events") or result.get("entries") or result.get("items") or []
        print(f"AUDIT_EVENTS_COUNT={len(items) if isinstance(items, list) else 0}", flush=True)
        if isinstance(items, list) and items:
            first = items[0]
            keys = list(first.model_dump().keys()) if hasattr(first, "model_dump") else (list(first.keys()) if isinstance(first, dict) else [])
            print(f"AUDIT_FIRST_KEYS={keys}", flush=True)
    except Exception as e:
        print(f"AUDIT_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
