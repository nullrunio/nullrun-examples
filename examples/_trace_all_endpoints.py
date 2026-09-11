"""End-to-end wire trace harness for every SDK endpoint.

Exercises every endpoint the SDK can hit and dumps the full wire
request/response bodies via ``_wire_tracer``. The goal is to spot
where the SDK sends a client-generated id where the backend expects
a server-minted one (or vice versa), and where the SDK silently
forwards a sentinel/placeholder value the backend may treat as a
real id.

Coverage:
  - POST /api/v1/auth/verify         (init)
  - GET  /api/v1/capabilities        (probe)
  - POST /api/v1/gate                (allow + require_approval + block)
  - POST /api/v1/execute             (allow + re-check after approve)
  - POST /api/v1/track               (single-event v3 path)
  - POST /api/v1/track/batch         (legacy batch path)
  - POST /api/v1/cancel              (cancel an execution)
  - POST /api/v1/heartbeat           (chain TTL extension)
  - POST /api/v1/gate?chain_op=end   (chain_end)
  - GET  /api/v1/budget/approximate  (UI read)
  - GET  /api/v1/orgs/{id}/audit-log (audit read)
  - GET  /api/v1/orgs/{id}/audit-log/verify (audit hash verify)
  - GET  /api/v1/orgs/{id}/audit-log/export (list)
  - POST /api/v1/orgs/{id}/audit-log/export (create)
  - GET  /api/v1/orgs/{id}/audit-log/export/{job_id}/status

Run from the examples directory so ``_env`` finds ``examples/.env``::

    PYTHONUNBUFFERED=1 .venv/Scripts/python.exe _trace_all_endpoints.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid

import _wire_tracer

_wire_tracer.install()

from _env import load_env  # noqa: E402

load_env()

from nullrun import (  # noqa: E402
    NullRunRuntime,
    init_or_die,
    set_call_context,
    shutdown,
)

init_or_die()


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)


def pause() -> None:
    """Give the WS listener + auth probe a moment to settle."""
    time.sleep(0.3)


def main() -> int:
    rt = NullRunRuntime()
    pause()

    # Inject set_call_context via runtime API (it's a function, not a
    # context manager) so the next /gate picks the model + tools.
    set_call_context(model="gpt-4o-mini", tools=())

    try:
        # ---- 1. /gate allow via direct check_workflow_budget ------------
        section("1. POST /api/v1/gate (allow path via check_workflow_budget)")
        try:
            rt.check_workflow_budget()
            print("  /gate allow: PASS", flush=True)
        except Exception as e:
            print(f"  /gate allow: {type(e).__name__}: {e}", flush=True)

        # ---- 2. /execute require_approval → WS approve → re-fire ---------
        section("2. POST /api/v1/execute (require_approval → WS approve → re-fire)")
        rt.add_sensitive_tool("refund_customer")

        def approve_in_bg() -> None:
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                with rt._approval_lock:
                    pending = dict(rt._approval_pending)
                if pending:
                    approval_id = next(iter(pending))
                    rt._handle_approval_resolved(
                        {
                            "approval_id": approval_id,
                            "outcome": "approved",
                            "note": "trace-harness approval",
                            "resolved_at": int(time.time()),
                        }
                    )
                    return
                time.sleep(0.02)

        t = threading.Thread(target=approve_in_bg, daemon=True)
        t.start()

        try:
            rt.execute(
                "refund_customer",
                {"kwargs": {"amount_cents": "5000", "currency": "USD"}},
                mode="strict",
            )
            print("  /execute require_approval → allow: PASS", flush=True)
        except Exception as e:
            print(f"  /execute require_approval: {type(e).__name__}: {e}", flush=True)
        t.join(timeout=2.0)

        # ---- 3. /gate block via OVER_BUDGET (real budget pressure) ------
        section("3. POST /api/v1/gate (block path)")

        # Use a giant token estimate to trigger a budget block.
        try:
            with set_call_context(model="gpt-4o-mini", tools=()):
                # Direct call to bypass the model-pricing cap on real
                # estimates — call the runtime's gate method with a
                # manufactured wire-body.
                rt._transport.check(
                    {
                        "organization_id": str(rt.organization_id),
                        "execution_id": str(uuid.uuid7()) if hasattr(uuid, "uuid7") else str(uuid.uuid4()),
                        "trace_id": str(uuid.uuid4()),
                        "tool": "fake",
                        "input": None,
                        "mode": "auto",
                        "check_type": "llm",
                        "model": "gpt-4o-mini",
                        "estimated_tokens": 10**12,
                        "operation_id": str(uuid.uuid4()),
                        "action_digest": "0" * 64,
                    }
                )
                print("  /gate block: unexpected allow", flush=True)
        except Exception as e:
            print(f"  /gate block: {type(e).__name__}: {e}", flush=True)

        # ---- 4. /track (single-event v3 path) ----------------------------
        section("4. POST /api/v1/track (single-event v3)")

        try:
            from nullrun.context import get_server_minted_execution_id

            smid_before = get_server_minted_execution_id()
            print(f"  server-minted execution_id available: {smid_before}", flush=True)
        except Exception as e:
            print(f"  cannot read server-minted id: {e}", flush=True)

        try:
            rt._route_track(
                {
                    "type": "llm_call",
                    "tool_name": "openai_chat",
                    "input_tokens": 100,
                    "output_tokens": 200,
                    "latency_ms": 1500,
                    "model": "gpt-4o-mini",
                    "trace_id": str(uuid.uuid4()),
                }
            )
            rt._transport.flush_now()
            print("  /track single: flushed", flush=True)
        except Exception as e:
            print(f"  /track single: {type(e).__name__}: {e}", flush=True)

        # ---- 5. /track/batch (legacy batch path) -------------------------
        section("5. POST /api/v1/track/batch (legacy batch)")

        try:
            rt._route_track(
                {
                    "type": "tool_call",
                    "tool_name": "some_tool",
                    "metadata": {"kind": "trace"},
                    "trace_id": str(uuid.uuid4()),
                }
            )
            rt._transport.flush_now()
            print("  /track/batch: flushed", flush=True)
        except Exception as e:
            print(f"  /track/batch: {type(e).__name__}: {e}", flush=True)

        # ---- 6. /cancel --------------------------------------------------
        section("6. POST /api/v1/cancel (cancel the captured execution_id)")

        try:
            from nullrun.context import get_server_minted_execution_id

            smid = get_server_minted_execution_id()
            if smid:
                result = rt.cancel_execution(smid, reason="trace-harness cancel")
                print(f"  /cancel: {result}", flush=True)
            else:
                print("  /cancel: SKIPPED — no server-minted id available", flush=True)
        except Exception as e:
            print(f"  /cancel: {type(e).__name__}: {e}", flush=True)

        # ---- 7. /heartbeat -----------------------------------------------
        section("7. POST /api/v1/heartbeat")

        try:
            from nullrun.context import set_chain_id

            chain_id = str(uuid.uuid4())
            set_chain_id(chain_id)
            set_call_context(model="gpt-4o-mini", tools=())
            rt.check_workflow_budget()
            result = rt.heartbeat(chain_id)
            print(f"  /heartbeat: {result}", flush=True)
        except Exception as e:
            print(f"  /heartbeat: {type(e).__name__}: {e}", flush=True)

        # ---- 8. /gate?chain_op=end (chain_end) ----------------------------
        section("8. POST /api/v1/gate (chain_end via Transport.chain_end)")

        try:
            from nullrun.context import get_chain_id

            cid = get_chain_id()
            if cid:
                rt.chain_end(cid)
                print("  chain_end: completed", flush=True)
            else:
                print("  chain_end: SKIPPED — no chain_id available", flush=True)
        except Exception as e:
            print(f"  chain_end: {type(e).__name__}: {e}", flush=True)

        # ---- 9. /budget/approximate --------------------------------------
        section("9. GET /api/v1/budget/approximate")

        try:
            result = rt.approximate_budget()
            print(
                "  /budget/approximate:",
                json.dumps(result, indent=2, sort_keys=True, default=str),
                flush=True,
            )
        except Exception as e:
            print(f"  /budget/approximate: {type(e).__name__}: {e}", flush=True)

        # ---- 10. /audit-log (list) ---------------------------------------
        section("10. GET /api/v1/orgs/{org_id}/audit-log")

        try:
            page = rt.audit.list(limit=5)
            print(
                "  /audit-log list:",
                json.dumps(page.to_wire(), indent=2, sort_keys=True, default=str)[:500],
                flush=True,
            )
        except Exception as e:
            print(f"  /audit-log list: {type(e).__name__}: {e}", flush=True)

        # ---- 11. /audit-log/verify ---------------------------------------
        section("11. GET /api/v1/orgs/{org_id}/audit-log/verify")

        try:
            result = rt.audit.verify()
            print(
                "  /audit-log/verify:",
                json.dumps(result, indent=2, sort_keys=True, default=str)[:500],
                flush=True,
            )
        except Exception as e:
            print(f"  /audit-log/verify: {type(e).__name__}: {e}", flush=True)

        # ---- 12. /audit-log/export (list + create) -----------------------
        section("12. GET /api/v1/orgs/{org_id}/audit-log/export (list)")
        try:
            listed = rt.audit.list_exports()
            print(f"  /audit-log/export list: {listed}", flush=True)
        except Exception as e:
            print(f"  /audit-log/export list: {type(e).__name__}: {e}", flush=True)

        section("13. POST /api/v1/orgs/{org_id}/audit-log/export (create)")
        try:
            created = rt.audit.create_export()
            print(f"  /audit-log/export create: {created}", flush=True)
            job_id = created.get("job_id") if isinstance(created, dict) else None
            if job_id:
                section(
                    f"14. GET /api/v1/orgs/{{org_id}}/audit-log/export/{job_id}/status"
                )
                try:
                    status = rt.audit.export_status(job_id)
                    print(f"  /audit-log/export status: {status}", flush=True)
                except Exception as e:
                    print(
                        f"  /audit-log/export status: {type(e).__name__}: {e}",
                        flush=True,
                    )
        except Exception as e:
            print(f"  /audit-log/export create: {type(e).__name__}: {e}", flush=True)

    finally:
        try:
            shutdown()
        except Exception:
            pass

    # Dump captured wire exchanges.
    print("\n\n", flush=True)
    _wire_tracer.dump()
    return 0


if __name__ == "__main__":
    sys.exit(main())
