"""Probe: trace exactly what exception class the approval demo hits on
the third refund (APPROVAL_REPLAY_REJECTED wire code).

Adds a sys.excepthook that prints the exception type, error_code
attribute, and full MRO before the typed arms have a chance to
swallow it.
"""
from __future__ import annotations
import sys
import traceback


def _excepthook(exc_type, exc_value, exc_tb):
    print("=" * 60, file=sys.stderr)
    print("PROBE: excepthook caught exception", file=sys.stderr)
    print(f"  type: {exc_type.__qualname__}", file=sys.stderr)
    print(f"  MRO: {[c.__qualname__ for c in exc_type.__mro__]}", file=sys.stderr)
    print(f"  error_code attribute: {getattr(exc_value, 'error_code', '<missing>')!r}", file=sys.stderr)
    print(f"  approval_id: {getattr(exc_value, 'approval_id', '<missing>')!r}", file=sys.stderr)
    print(f"  workflow_id: {getattr(exc_value, 'workflow_id', '<missing>')!r}", file=sys.stderr)
    print(f"  status_code: {getattr(exc_value, 'status_code', '<missing>')!r}", file=sys.stderr)
    print(f"  message: {exc_value}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)


sys.excepthook = _excepthook

# Now run the actual approval demo as a subprocess-like import
if __name__ == "__main__":
    # Run the demo module's main block via runpy
    import runpy
    sys.argv = ["langgraph_openai_approval_demo.py"]
    runpy.run_path(
        "langgraph_openai_approval_demo.py",
        run_name="__main__",
    )
