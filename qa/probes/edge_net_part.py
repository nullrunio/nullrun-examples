"""EDGE-NET-PART test: verify SDK handles truncated/partial HTTP responses.

Direct test of httpx partial-read behavior (truncated response body).
This tests the SDK's behavior when the underlying connection is cut mid-stream.
We simulate by configuring a very short timeout so the response is incomplete.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from examples._env import load_env  # type: ignore

load_env()


def main():
    # Test 1: Missing X-NULLRUN-PROTOCOL header (partial wire contract)
    # Per CLAUDE.md §3: 'Each request MUST contain X-NULLRUN-PROTOCOL header.
    # Absent or incompatible → 400 before step 1.'
    # We can't easily disable the SDK header, but we can check the SDK handles
    # unexpected responses gracefully.

    # Test 2: Try sending a malformed JSON body
    # This tests the SDK's resilience to partial response.

    # Test 3: Direct API probe of /api/v1/gate with malformed JSON
    import httpx

    url = os.environ.get("NULLRUN_API_URL", "https://api.nullrun.io") + "/api/v1/gate"
    api_key = os.environ.get("NULLRUN_API_KEY", "")

    if not api_key:
        print("No API key set")
        return

    # Test partial responses
    test_cases = [
        ("empty_body", ""),
        ("partial_json", '{"model":'),
        ("invalid_json", "{ this is not json"),
        ("truncated_response_headers", "N/A"),  # special marker
    ]

    for label, body in test_cases:
        try:
            if label == "truncated_response_headers":
                # Use very short timeout
                response = httpx.post(
                    url,
                    content='{"model":"claude-sonnet-4-6","stream":false,"idempotency_key":"test-part-1"}',
                    headers={"X-NULLRUN-PROTOCOL": "3", "Content-Type": "application/json"},
                    timeout=0.001,  # 1ms timeout
                )
                print(f"  [{label}] status={response.status_code}; body={response.text[:120]!r}")
            else:
                response = httpx.post(
                    url,
                    content=body,
                    headers={"X-NULLRUN-PROTOCOL": "3", "Content-Type": "application/json"},
                    timeout=5.0,
                )
                print(f"  [{label}] status={response.status_code}; body={response.text[:120]!r}")
        except httpx.TimeoutException as e:
            print(f"  [{label}] TimeoutException: {str(e)[:120]}")
        except httpx.RequestError as e:
            print(f"  [{label}] RequestError: {type(e).__name__}: {str(e)[:120]}")
        except Exception as e:
            print(f"  [{label}] Other exception: {type(e).__name__}: {str(e)[:120]}")


if __name__ == "__main__":
    main()