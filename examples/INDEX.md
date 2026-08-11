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

| File | What it shows |
|---|---|
| `qa/probes/probe_rate_burst.py` | Sequential `@protect` calls; counts allow/block per iteration |
| `qa/probes/probe_rate_burst_nollm.py` | Same as above but skips the real LLM call |
| `qa/probes/probe_rate_S07.py` | RATE-01..04 — cap=5/min, expect 5 ALLOW + 3 BLOCK |
| `qa/probes/probe_tb_S07.py` | TB-01..09 — parameterized tool-list + chain context |
| `qa/probes/probe_bud_above.py` | Single `@protect` against a $0.00 budget workflow |
| `qa/probes/probe_bud_below_nollm.py` | Below-threshold verification without LLM calls |
| `qa/probes/probe_apikey_revoke.py` | Captures the exact HTTP response on a revoked key |
| `qa/probes/s3_api_keys_test.py` | Smoke test for API-key prefix handling |
| `qa/approval_rules/ar_toolname_run.py` | Approval-rule probe — `TOOLNAME` matcher |
| `qa/approval_rules/ar_toolname_run_chain.py` | Same as above inside a `chain()` context |
| `qa/approval_rules/ar_params_run.py` | Approval-rule probe — `PARAMS` matcher (`force=true`) |
| `smoke_test.py` | Minimal SDK init verification |

## Tools

| File | Purpose |
|---|---|
| `tools/synthetic_sdk_load.py` | Bounded load against an authorized backend (CLI) |

## Shared helpers

| File | Purpose |
|---|---|
| `_env.py` | Loads `examples/.env` into `os.environ` (no-op without python-dotenv) |
| `_boilerplate.py` | `example_run()` context manager — folds `load_env()` + `init_or_die()` + `shutdown()` |
