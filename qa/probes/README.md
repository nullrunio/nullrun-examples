# QA Probes

Family-A (SDK-level) and Family-B (wire-level) probes for NULLRUN
SDK + backend integration. Each probe is a standalone Python script
that can be run against a live NULLRUN deployment.

## Probe families

### Family A — SDK-level (drive the SDK)

| Probe | Verifies |
|---|---|
| `probe_tc10_hard.py` | Hard budget block (BUDGET_HARD_BLOCKED) |
| `probe_tc11_soft.py` / `probe_tc11_soft_v2.py` | Soft pass / SOFT_PASS flow |
| `probe_tc15_approval_chain.py` | Approval flow inside chain context |
| `probe_rate_burst*.py` | Per-workflow rate limit (4 variants) |
| `probe_rate_S07.py` | 8 sequential no-LLM gate calls |
| `probe_bud_*.py` | Budget above/below threshold |
| `rate_limit_demo.py` (Tier-1) | NR-R001 / NR-R002 typed raise |
| `approval_required_demo.py` (Tier-1) | NR-A010..A015 typed raise |
| `chain_mismatch_demo.py` (Tier-1) | NR-CH001 typed raise |

### Family B — wire-level (raw httpx)

| Probe | Verifies |
|---|---|
| `wire_protocol.py` | X-NULLRUN-PROTOCOL header (TC-SDKG-001..004) |
| `wire_exec_id.py` | Server-minted UUIDv7 (TC-SDKG-005) |
| `wire_proj_cost.py` | Server-computed projected_cost_cents (TC-SDKG-008) |
| `wire_contract_protocol.py` | Full wire contract via /api/v1/gate |
| `wire_contract_track_batch.py` | /track batch behaviour |
| `wire_gate_probe.py` | HMAC-signed /gate probe |
| `hmac_stack.py` | HMAC signature stack (colon-separated) |
| `edge_net_*.py` | Network edge cases (timeout / partial / retry) |
| `edge_inv_chain.py` / `edge_par_chain.py` | Chain edge cases |
| `langgraph_openai_wire_contract_demo.py` | Multi-agent LangGraph wire contract |

## Endpoint migration (2026-09-10)

The `/api/v1/check` endpoint was removed in the v3 consolidation
(2026-06-27) and replaced by `/api/v1/gate`. As of this batch
(2026-09-10), all Family-B probes that POSTed directly to
`/api/v1/check` were migrated:

- `wire_protocol.py`
- `wire_exec_id.py`
- `wire_proj_cost.py`
- `langgraph_openai_wire_contract_demo.py` (TC-SDK-047 worker)

Each migrated probe carries an `Endpoint migration (2026-09-10)`
docstring note explaining why the path changed and what the test
contract now asserts. The probe bodies were kept identical apart
from the URL — the wire shape (auth header, protocol header,
JSON body) is unchanged so the test contracts (TC-SDKG-001..008)
are preserved.

If you find a probe that still POSTs to `/api/v1/check`, it is
stale and will get 404 instead of the test-contract response.
Either migrate it following the pattern above or delete it.

## Running a probe

```bash
# Source credentials
export NULLRUN_API_URL=https://api.nullrun.io
export NULLRUN_API_KEY=nr_live_...
export NULLRUN_ORG_ID=...
export NULLRUN_WORKFLOW_ID=...

# Family-A (SDK-level — needs `from nullrun import init_or_die`)
python qa/probes/rate_limit_demo.py

# Family-B (wire-level — raw httpx)
python qa/probes/wire_protocol.py
```

## Verdict vocabulary

- `PASS` — probe met its expected outcome
- `BLOCK` — backend returned a wire-shape-correct block
- `REVIEW` — outcome needs human inspection (typed class missing,
  unexpected exception type, etc.)
- `ERROR` — probe itself failed (network, auth, syntax)
- `SETUP-FAIL` — environment setup wrong (see `setup_assertions.py`)
