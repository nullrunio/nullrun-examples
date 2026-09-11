# Examples index

Categorized map of every runnable file in this repo. Use this when you
want "one example for framework X" without scrolling the README. The
top-level README links here for the demos and probes tables.

## Basic — one per vendor / framework (≤ 80 lines each)

| File | Vendor | What it shows |
|---|---|---|
| `raw_openai_basic.py` | OpenAI | `@protect` + `@guarded` on a single LLM call |
| `anthropic_basic.py` | Anthropic | `@protect` + `@guarded` on `messages.create` |
| `mistral_basic.py` | Mistral | `@protect` + `@guarded` on `chat.complete` |
| `gemini_basic.py` | Gemini | `@protect` + `@guarded` on `models.generate_content` |
| `cohere_basic.py` | Cohere | `@protect` + `@guarded` on `client.chat` (V2) |
| `bedrock_basic.py` | AWS Bedrock | `@protect` + manual `track_llm` (boto3 uses urllib3, not httpx) |
| `langchain_basic.py` | LangChain | Auto-instrumented `ChatModel.invoke` (not via LangGraph) |
| `langgraph_basic.py` | LangGraph | Auto-instrumented `StateGraph` (recommended) |
| `langgraph_manual_wrapper.py` | LangGraph | `nullrun.toolbox.langgraph.wrapper` for re-compiled graphs |
| `llama_index_basic.py` | llama-index | Auto-instrumented `LLMChatEndEvent` / `FunctionCallEvent` |
| `crewai_basic.py` | CrewAI | Auto-instrumented `Crew.kickoff` + `usage_metrics` flush |
| `autogen_basic.py` | AutoGen | Auto-instrumented `BaseChatAgent.on_messages` |
| `openai_agents_basic.py` | OpenAI Agents SDK | `@protect` + `@guarded` on a multi-step agent run |

## Policies — guardrails

| File | What it shows |
|---|---|
| `cost_cap_demo.py` | Hard budget cap that halts the agent |
| `chain_soft_mode.py` | Soft-mode pass via active `chain` context |
| `on_error_hook.py` | `nullrun.on_error` hook for Sentry / dashboards |

## Demos — larger end-to-end walk-throughs

| File | What it shows |
|---|---|
| `gate_check_demo.py` | `/gate` pre-flight probe, no LLM, tool-name semantics |
| `tool_params_demo.py` | Phase 1 / MVP 1.1 ToolParameters — three decorator shapes |
| `langgraph_openai_approval_demo.py` | LangGraph agent + `refund_customer` + approval rule |
| `langgraph_openai_mcp_demo.py` | LangGraph + OpenAI + in-process MCP server (Разрыв 3) |

## Probes — internal QA only (not for end-users)

These scripts assume specific workflows are configured on the dashboard
and dump raw SDK wire traffic. They are **not** in the public README.

The `qa/` subtree is laid out by intent:

- `qa/probes/` — flow-level probes (rate / budget / tool-block / auth).
  Each one targets a specific wire path or backend behaviour.
- `qa/approval_rules/` — Approval-Rule probes that fire specific
  matchers (`TOOLNAME`, `PARAMS`) and assert the operator-side WS-push
  flow end-to-end.
- `qa/logs/` — default output destination for the probes that log
  per-scenario artifacts (`probe_tb_S07.py` writes
  `S07-TB-probe.log`, `probe_rate_S07.py` writes
  `S07-RATE-probe.log`, `s3_api_keys_test.py` writes
  `s3_api_keys.json`). Overridable per-probe via `LOG_PATH` /
  `EVIDENCE_PATH` env vars.

`__init__.py` files in `qa/`, `qa/probes/`, and `qa/approval_rules/`
are empty package markers — kept so the subtrees are importable from
the repo root `sys.path` insertion the probes rely on.

| File | What it shows |
|---|---|
| `qa/probes/probe_rate_burst.py` | 30 sequential `@protect`-wrapped real OpenAI gpt-4o-mini calls; logs `allow`/`block` per iteration + `first_block` index |
| `qa/probes/probe_rate_burst_nollm.py` | 8 `runtime.check_workflow_budget()` calls (no LLM cost) on cap=5/min workflow; expects `first_block=5` |
| `qa/probes/probe_rate_S07.py` | RATE-01..04 — 8 gate calls via `runtime.check_workflow_budget()`, expect 5 ALLOW + 3 BLOCK on cap=5/min |
| `qa/probes/probe_rate_burst_two_keys.py` | RATE-H2 — 8×`check_workflow_budget()` per key via two fresh `NullRunRuntime` instances (bypasses the singleton so each burst owns its key); reads `details.scope` discriminator on the v3.53 org-aggregate wire |
| `qa/probes/probe_tb_S07.py` | TB-01..09 — `set_call_context(tools=...)` + one `check_workflow_budget()` per scenario; patches `Transport.check` to dump req/resp JSON to a per-scenario log |
| `qa/probes/probe_bud_above.py` | Single `@protect` OpenAI call against a $0.00-budget workflow; expects `BUDGET_*` block + surfaces `error_code` |
| `qa/probes/probe_bud_below_nollm.py` | 3 `runtime.check_workflow_budget()` calls (no LLM) against $5.00-budget workflow; expects all ALLOW |
| `qa/probes/probe_apikey_revoke.py` | Patches `httpx.Client.send` to dump status+headers+body to stderr + `PROBE_LOG_PATH`; one `check_workflow_budget()` against a `TEST_API_KEY` env-supplied key (intended for revoked-key verification) |
| `qa/probes/s3_api_keys_test.py` | 7-scenario API-key + tool-name smoke (valid×3 tools, random invalid, empty, garbage, `nr_test_` prefix); re-`init()` per scenario; writes JSON evidence to `qa/logs/` |
| `qa/probes/edge_net_timeout.py` | EDGE-NET-TIMEOUT — `NULLRUN_API_URL=.invalid` + fake key + `importlib.reload(nullrun)`; expects auth or DNS failure and the gate's fail-OPEN decision |
| `qa/probes/edge_net_part.py` | EDGE-NET-PART — raw `httpx.post` against `/api/v1/gate` (bypasses SDK) with empty / partial-JSON / invalid-JSON / 1ms-timeout bodies to exercise wire-only handling |
| `qa/probes/edge_net_retry.py` | EDGE-NET-RETRY — `set_call_context(idempotency_key=K)` + 5×`check_workflow_budget()` with the same K; expects 1 distinct `execution_id` (CLAUDE.md §15 replay) |
| `qa/probes/edge_inv_chain.py` | EDGE-INV-CHAIN — 7 invalid `chain_id` shapes (non-UUID, numeric, special chars, partial, empty, all-zero UUID, all-f UUID) through `set_call_context` + `check_workflow_budget`; observes error type / decision per shape |
| `qa/probes/edge_par_chain.py` | EDGE-PAR-CHAIN — `asyncio.gather` of 5 `check_workflow_budget()` calls with distinct `chain_id`s; observes concurrency + per-task decision |
| `qa/probes/debug_gate.py` | Patches `httpx.Client.send` to dump every SDK HTTP request/response body to stderr; diagnostic helper for wire-shape investigations — not a customer-facing example |
| `qa/probes/probe_load_check.py` | TS-12e load-test setup check — single `check_workflow_budget(tool="bash")` against hardcoded workflow `2af6d075-7ce0-4f7e-b3b5-55c714431dff`; reads `NULLRUN_API_KEY` only, no extra env vars |
| `qa/probes/langgraph_openai_wire_contract_demo.py` | LangGraph workers exercising wire-level rejection paths (`X-NULLRUN-PROTOCOL: 1` / `4` / absent); SDK-derived init + raw `httpx.post` for the wire-probe workers — operator-only |
| `qa/probes/langgraph_openai_observability_demo.py` | LangGraph workers probing observability fail-CLOSED surfaces (ApproximateBudget 503, trace ingestion 503, retrieval 503 + Retry-After, rate-limit 503) — HTTP-only because the probe needs raw response inspection |
| `qa/approval_rules/ar_toolname_run.py` | Approval-rule probe — single `refund_customer` call (amount from CLI) fires the `TOOLNAME` matcher and blocks via WS push |
| `qa/approval_rules/ar_toolname_run_chain.py` | Same as above wrapped in `with chain(...)` to force `chain_ok=true` (workaround for the binary that treats `HARD_BUDGET_EXCEEDED` as soft-blocked otherwise) |
| `qa/approval_rules/ar_params_run.py` | Approval-rule probe — `delete_user_auto(force=…)` from CLI; the `PARAMS` matcher (`force=true`) fires only when `True` |
| `qa/approval_rules/ar_threshold_run.py` | Approval-rule probe — `refund_customer(amount from CLI)` for the TOOLS-ABOVE matcher; same WS-push wait as `ar_toolname_run.py`, parameterized by amount so the three comparator variants (`exceeds` / `equals or exceeds` / `equals`) can be exercised from a shell wrapper |
| `qa/approval_rules/ar_dnf_run.py` | Approval-rule probe — 4-arg `process_transaction(region, credit, total, criminal)` for the TOOLS-MATCH Custom DNF matcher; exercises `(region ∈ {EU,US} ∧ credit=true) ∨ (total ∈ [100,500] ∧ criminal=true)` from a shell wrapper scenario matrix |
| `smoke_test.py` | `init_or_die()` + `status()` round-trip — minimal SDK reachability check |

## Tools

CLI / ops scripts that live outside the `examples/` tree. They
exercise the SDK from outside the example corpus (no `_boilerplate.py`,
no shared `init_or_die()` wrapper).

| File | Purpose |
|---|---|
| `tools/synthetic_sdk_load.py` | Bounded load against an authorized backend (CLI) — drives `/gate` + `/track` from a thread pool at a configurable rate; `--dry-run` schedules without HTTP |

## Shared helpers

| File | Purpose |
|---|---|
| `_env.py` | Loads `examples/.env` into `os.environ` (no-op without python-dotenv) |
| `_boilerplate.py` | `example_run()` context manager — folds `load_env()` + `init_or_die()` + `shutdown()` |
