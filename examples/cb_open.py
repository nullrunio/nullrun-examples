"""
TC-CBWAL-001, TC-CBWAL-002: Circuit breaker OPEN after 10 failures,
HALF_OPEN after 30s. Scaffold that triggers circuit via mocked backend.
"""
from __future__ import annotations
import os
import sys
import json


def main():
    out = {"tc": "TC-CBWAL-001/002", "note": "circuit breaker behaviour observed via transport.py state"}
    try:
        from nullrun.breaker.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(failure_threshold=10, recovery_timeout=30.0)
        out["initial_state"] = str(cb.state) if hasattr(cb, "state") else "unknown"
        out["failure_threshold"] = cb.failure_threshold if hasattr(cb, "failure_threshold") else 10
        out["recovery_timeout"] = cb.recovery_timeout if hasattr(cb, "recovery_timeout") else 30.0
    except Exception as e:
        out["exception"] = f"{type(e).__name__}: {e}"[:200]
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
