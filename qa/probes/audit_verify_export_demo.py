"""Probe for TC-19 — /audit-log/verify + /audit-log/export job creation."""
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

    # /audit-log/verify — hash chain verification
    try:
        verify_result = rt.audit.verify()
        print(f"AUDIT_VERIFY={verify_result}", flush=True)
    except Exception as e:
        print(f"AUDIT_VERIFY_FAIL: {type(e).__name__}: {e}", flush=True)

    # /audit-log/export — create export job
    try:
        export_result = rt.audit.create_export()
        print(f"AUDIT_EXPORT={export_result}", flush=True)
        if isinstance(export_result, dict):
            job_id = export_result.get("job_id") or export_result.get("id") or export_result.get("export_id")
            if job_id:
                print(f"AUDIT_EXPORT_JOB_ID={job_id}", flush=True)
    except Exception as e:
        print(f"AUDIT_EXPORT_FAIL: {type(e).__name__}: {e}", flush=True)

    print("CHAIN_LIFECYCLE_COMPLETE", flush=True)
    shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
