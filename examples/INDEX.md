# Examples index

Categorized map of every runnable file in this repo. Use this when you
want "one example for framework X" without scrolling the README. The
top-level README links here for the demos and probes tables.

## Basic — one per vendor / framework (≤ 80 lines each)

SDK 0.18.1+: every example uses lazy-init — the first `@protect`
call creates the runtime, attaches the framework hook, and prints
the four-line developer report on any `NullRunError` via
`with nullrun.handle():`. See `docs/concepts/error-handling.md`
for the full pattern.

| File | Vendor | What it shows |
|---|---|---|
| `raw_openai_basic.py` | OpenAI | `@protect` on a single LLM call (lazy-init) |
| `anthropic_basic.py` | Anthropic | `@protect` on `messages.create` (lazy-init) |
| `mistral_basic.py` | Mistral | `@protect` on `chat.complete` (lazy-init) |
| `gemini_basic.py` | Gemini | `@protect` on `models.generate_content` (lazy-init) |
| `cohere_basic.py` | Cohere | `@protect` on `client.chat` (V2) (lazy-init) |
| `bedrock_basic.py` | AWS Bedrock | `@protect` + manual `track_llm` (boto3 uses urllib3, not httpx) |
| `langchain_basic.py` | LangChain | Auto-instrumented `ChatModel.invoke` (not via LangGraph) |
| `langgraph_basic.py` | LangGraph | Auto-instrumented `StateGraph` (recommended) |
| `langgraph_manual_wrapper.py` | LangGraph | `nullrun.patch_langgraph_compiled` for late-compiled graphs (replaces deprecated `wrapper()`) |
| `llama_index_basic.py` | llama-index | Auto-instrumented `LLMChatEndEvent` / `FunctionCallEvent` |
| `crewai_basic.py` | CrewAI | Auto-instrumented `Crew.kickoff` + `usage_metrics` flush |
| `autogen_basic.py` | AutoGen | Auto-instrumented `BaseChatAgent.on_messages` |
| `openai_agents_basic.py` | OpenAI Agents SDK | `@protect` on a multi-step agent run (lazy-init) |

## Policies — guardrails

| File | What it shows |
|---|---|
| `cost_cap_demo.py` | Hard budget cap that halts the agent |
| `chain_soft_mode.py` | Soft-mode pass via active `chain` context |
| `on_error_hook.py` | `nullrun.on_error` hook + `with nullrun.handle():` for Sentry / dashboards |

## Demos — larger end-to-end walk-throughs

| File | What it shows |
|---|---|
| `gate_check_demo.py` | `/gate` pre-flight probe, no LLM, tool-name semantics |
| `tool_params_demo.py` | Phase 1 / MVP 1.1 ToolParameters — three decorator shapes (`@protect`, `@protect @sensitive(impact=tool_params({...}))`, `@protect @sensitive(impact=money_outflow(...))`). |
| `protect_only_public_api_demo.py` | SDK 0.18.1 `@protect`-only public API — auto-attach of default `ToolParamsExtractor`, bounded extraction (1024-byte truncation + cycle guard + aggregate DEBUG log), and the typed-extractor path. No LLM, no backend needed. |
| `langgraph_openai_approval_demo.py` | LangGraph agent + `refund_customer` + approval rule |
| `langgraph_openai_mcp_demo.py` | LangGraph + OpenAI + in-process MCP server (Разрыв 3) |

## Probes — internal QA only (not for end-users)

These scripts assume specific workflows are configured on the dashboard
and dump raw SDK wire traffic. They are **not** in the public README.

The probe suite lives outside this `examples/` directory (under
`internal/qa/` in the repo root). It is laid out by intent:

- `internal/qa/probes/` — flow-level probes (rate / budget /
  tool-block / auth). Each one targets a specific wire path or
  backend behaviour.
- `internal/qa/approval_rules/` — Approval-Rule probes that fire
  specific matchers (`TOOLNAME`, `PARAMS`) and assert the
  operator-side WS-push flow end-to-end.
- `internal/qa/logs/` — default output destination for the probes
  that log per-scenario artifacts. Overridable per-probe via
  `LOG_PATH` / `EVIDENCE_PATH` env vars.

`__init__.py` files in `internal/qa/` and its subdirectories are
empty package markers — kept so the subtrees are importable from
the repo root `sys.path` insertion the probes rely on.

See the [probes README](internal/qa/probes/README.md) for the full
list of probes and what each one exercises. The most common ones
to know about:

| Probe | What it shows |
|---|---|
| `probe_rate_burst.py` | 30 sequential `@protect`-wrapped real OpenAI gpt-4o-mini calls; logs `allow`/`block` per iteration + `first_block` index |
| `probe_rate_burst_nollm.py` | 8 `runtime.check_workflow_budget()` calls (no LLM cost) on cap=5/min workflow; expects `first_block=5` |
| `probe_rate_S07.py` | RATE-01..04 — 8 gate calls via `runtime.check_workflow_budget()`, expect 5 ALLOW + 3 BLOCK on cap=5/min |
| `probe_tb_S07.py` | TB-01..09 — `set_call_context(tools=...)` + one `check_workflow_budget()` per scenario; patches `Transport.check` to dump req/resp JSON to a per-scenario log |
| `probe_bud_above.py` | Single `@protect` OpenAI call against a $0.00-budget workflow; expects `BUDGET_*` block + surfaces `error_code` |
| `probe_apikey_revoke.py` | Patches `httpx.Client.send` to dump status+headers+body to stderr + `PROBE_LOG_PATH`; one `check_workflow_budget()` against a `TEST_API_KEY` env-supplied key (intended for revoked-key verification) |
| `s3_api_keys_test.py` | 7-scenario API-key + tool-name smoke (valid×3 tools, random invalid, empty, garbage, `nr_test_` prefix); re-`init()` per scenario; writes JSON evidence to the logs dir |
| `edge_net_timeout.py` | EDGE-NET-TIMEOUT — `NULLRUN_API_URL=.invalid` + fake key + `importlib.reload(nullrun)`; expects auth or DNS failure and the gate's fail-OPEN decision |
| `edge_net_part.py` | EDGE-NET-PART — raw `httpx.post` against `/api/v1/gate` (bypasses SDK) with empty / partial-JSON / invalid-JSON / 1ms-timeout bodies to exercise wire-only handling |
| `edge_net_retry.py` | EDGE-NET-RETRY — `set_call_context(idempotency_key=K)` + 5×`check_workflow_budget()` with the same K; expects 1 distinct `execution_id` (CLAUDE.md §15 replay) |
| `edge_inv_chain.py` | EDGE-INV-CHAIN — 7 invalid `chain_id` shapes (non-UUID, numeric, special chars, partial, empty, all-zero UUID, all-f UUID) through `set_call_context` + `check_workflow_budget`; observes error type / decision per shape |
| `edge_par_chain.py` | EDGE-PAR-CHAIN — `asyncio.gather` of 5 `check_workflow_budget()` calls with distinct `chain_id`s; observes concurrency + per-task decision |
| `debug_gate.py` | Patches `httpx.Client.send` to dump every SDK HTTP request/response body to stderr; diagnostic helper for wire-shape investigations — not a customer-facing example |
| `ar_toolname_run.py` | Approval-rule probe — single `refund_customer` call (amount from CLI) fires the `TOOLNAME` matcher and blocks via WS push |
| `ar_params_run.py` | Approval-rule probe — `delete_user_auto(force=…)` from CLI; the `PARAMS` matcher (`force=true`) fires only when `True` |
| `ar_threshold_run.py` | Approval-rule probe — `refund_customer(amount from CLI)` for the TOOLS-ABOVE matcher; same WS-push wait as `ar_toolname_run.py`, parameterized by amount so the three comparator variants (`exceeds` / `equals or exceeds` / `equals`) can be exercised from a shell wrapper |
| `ar_dnf_run.py` | Approval-rule probe — 4-arg `process_transaction(region, credit, total, criminal)` for the TOOLS-MATCH Custom DNF matcher; exercises `(region ∈ {EU,US} ∧ credit=true) ∨ (total ∈ [100,500] ∧ criminal=true)` from a shell wrapper scenario matrix |
| `smoke_test.py` (this directory) | `init_or_die()` + `status()` round-trip — minimal SDK reachability check |

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
