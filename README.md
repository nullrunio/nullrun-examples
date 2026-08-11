# nullrun-examples

Working examples for the
[nullrun Python SDK](https://github.com/nullrunio/nullrun-sdk-python).

Each example is a self-contained, runnable file. The intent is to show
the smallest possible change to add enforcement to a common agent
framework.

For a categorized map (basic / policies / demos / probes), see
[`examples/INDEX.md`](./examples/INDEX.md). The README below covers
only the basic + policies tiers.

## Prerequisites

```bash
pip install nullrun
export NULLRUN_API_KEY=nr_live_...
```

Get an API key from the [NullRun dashboard](https://app.nullrun.io).

### Security notice — read this first

* `examples/.env` (real keys) is gitignored — **never** commit it.
* If a key ever appeared in `.env.backup` or any plain‑text file, treat
  it as compromised: rotate from the NullRun dashboard and from the
  vendor (OpenAI / Anthropic / ...) immediately. Disk‑only exposure
  is still exposure (cloud sync, lost laptop, shared screen recording).
* Use a short‑lived key for local dev. Use a CI‑only key for smoke runs.

### Shared `.env` (recommended)

Every example reads its keys from `examples/.env` if
[`python-dotenv`](https://pypi.org/project/python-dotenv/) is
installed (`pip install python-dotenv`) — no shell `export` needed.
Copy the template and fill in your keys:

```bash
cp examples/.env.example examples/.env
$EDITOR examples/.env   # set NULLRUN_API_KEY + per-vendor keys
python examples/raw_openai_basic.py
```

Without `python-dotenv` the examples fall back to whatever the
developer's shell already has exported — the auto-load is purely a
convenience. `examples/.env` is in `.gitignore`; commit only
`.env.example`.

## Auto-instrumentation

`nullrun.init(api_key=...)` patches the underlying HTTP transport and any
imported agent framework (`openai`, `openai-agents`, `langgraph`,
`autogen`, `crewai`, `llama-index`, ...) automatically. You get cost tracking
without changing your call sites; `@protect` is the **gate** layer (budget /
kill / pause) that runs *before* the call.

For frameworks that ship an extra, install with the matching optional
dependency (`nullrun[langgraph]`, `nullrun[openai]`,
`nullrun[anthropic]`, `nullrun[mistral]`, `nullrun[gemini]`,
`nullrun[cohere]`, `nullrun[bedrock]`, `nullrun[agents]`,
`nullrun[langchain]`, `nullrun[llama-index]`, `nullrun[crewai]`,
`nullrun[autogen]`). The `openai-agents` SDK is auto-detected at runtime
without a separate extra.

## Examples

| File | Framework | What it shows |
| --- | --- | --- |
| [`raw_openai_basic.py`](./examples/raw_openai_basic.py) | raw OpenAI | `@protect` + `@guarded` on a single LLM call |
| [`anthropic_basic.py`](./examples/anthropic_basic.py) | raw Anthropic | `@protect` + `@guarded` on a `messages.create` call |
| [`mistral_basic.py`](./examples/mistral_basic.py) | raw Mistral | `@protect` + `@guarded` on a `chat.complete` call |
| [`gemini_basic.py`](./examples/gemini_basic.py) | raw Gemini | `@protect` + `@guarded` on `models.generate_content` |
| [`cohere_basic.py`](./examples/cohere_basic.py) | raw Cohere | `@protect` + `@guarded` on `client.chat` (V2) |
| [`bedrock_basic.py`](./examples/bedrock_basic.py) | AWS Bedrock | `@protect` + manual `track_llm` (boto3 uses urllib3, not httpx) |
| [`langchain_basic.py`](./examples/langchain_basic.py) | LangChain | Auto-instrumented `ChatModel.invoke` (not via LangGraph) |
| [`langgraph_basic.py`](./examples/langgraph_basic.py) | LangGraph | Auto-instrumented `StateGraph` (recommended) |
| [`langgraph_manual_wrapper.py`](./examples/langgraph_manual_wrapper.py) | LangGraph | `nullrun.toolbox.langgraph.wrapper` for re-compiled graphs |
| [`llama_index_basic.py`](./examples/llama_index_basic.py) | llama-index | Auto-instrumented `LLMChatEndEvent` / `FunctionCallEvent` |
| [`crewai_basic.py`](./examples/crewai_basic.py) | CrewAI | Auto-instrumented `Crew.kickoff` + `usage_metrics` flush |
| [`autogen_basic.py`](./examples/autogen_basic.py) | AutoGen | Auto-instrumented `BaseChatAgent.on_messages` |
| [`openai_agents_basic.py`](./examples/openai_agents_basic.py) | OpenAI Agents SDK | `@protect` + `@guarded` on a multi-step agent run |
| [`cost_cap_demo.py`](./examples/cost_cap_demo.py) | any | Hard budget cap that halts the agent |
| [`chain_soft_mode.py`](./examples/chain_soft_mode.py) | any | Soft-mode pass via active `chain` context |
| [`on_error_hook.py`](./examples/on_error_hook.py) | any | `nullrun.on_error` hook for Sentry / dashboards |

Larger demos (LangGraph + approval rule, LangGraph + MCP, ToolParameters,
gate pre-flight) live under [`examples/INDEX.md`](./examples/INDEX.md#demos--larger-end-to-end-walk-throughs).
QA probes are also listed there under **Probes** — they are not
documented here because they assume specific workflow configurations.

## Running

```bash
export NULLRUN_API_KEY=nr_live_...
python examples/raw_openai_basic.py
```

All examples are read-only — they do not modify org state, policies, or
keys on your account. They **do** emit `track` events to the gateway
(auto-instrumented HTTP traffic from `init()`), so a `cost_attribution` or
`examples` tag in the dashboard will pick them up.

Every example ends with `nullrun.shutdown()` in a `finally` block. This
sends a clean WebSocket close frame so the backend does not log
`"Connection reset without closing handshake"` on long-running scripts.
No-op if `init()` was never called.

## Error handling in 0 lines

The examples intentionally avoid any `try/except NullRunError` block.
Three one-liners from the SDK do the work:

* `nullrun.init_or_die(api_key=...)` — wraps `nullrun.init()` so a
  missing `NULLRUN_API_KEY` produces a clean exit, not a raw
  traceback.
* `@nullrun.guarded` (decorator) — wrap a function so any
  `NullRunError` is translated into `format_user_message(exc)` on
  stderr and `sys.exit(1)`.
* `with nullrun.handle():` (context manager) — same behaviour for a
  region of code.

All three propagate `WorkflowKilledInterrupt` (a `BaseException`)
unchanged — kill signals must reach the top of the agent loop.
Non-NullRun exceptions also propagate so user bugs surface as honest
tracebacks.

For observability, register a hook with `nullrun.on_error(...)`. The
hook fires before every `NullRunError` raise with the structured
fields (`error_code`, `retryable`, `user_action`, `docs_url`,
`stage`, `workflow_id`) — pair it with `@guarded` for Sentry /
dashboards:

```python
import nullrun

@nullrun.on_error
def _to_sentry(err, ctx):
    sentry_sdk.capture_exception(err, extra={
        "error_code": err.error_code,
        "retryable": err.retryable,
        "stage": ctx.stage,
        "workflow_id": ctx.workflow_id,
    })
```

If you need to branch on a specific `error_code` (operator dashboards,
per-code retry policies), reach for `nullrun.NullRunError.error_code`
and the structured fields — see the
[error code catalogue](https://github.com/nullrunio/nullrun-sdk-python/blob/master/docs/errors/README.md)
for the full list. But for the common "run an agent and print a
friendly message on failure" case, `init_or_die` + `@guarded` /
`handle` is enough.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Connection reset without closing handshake` on the backend | forgot `shutdown()` in a long-running script | add `nullrun.shutdown()` in `finally` (every example already does) |
| `NR-B004 NullRunBudgetError` after a few calls | workflow budget exhausted on the dashboard | raise the cap or wait for the reset |
| `WorkflowKilledInterrupt` propagates up | operator clicked "kill" on the dashboard | expected; the agent loop sees it as a `BaseException` and exits cleanly |
| `init_or_die()` exits with a clean message | `NULLRUN_API_KEY` not set | `cp examples/.env.example examples/.env` and fill it in |
| `ImportError: mcp.server` in the MCP demo | `modelcontextprotocol` not installed | `pip install "nullrun[langgraph,mcp]"` |

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md). Keep each basic example
under 80 lines. No external state beyond the NullRun API key. Use the
shared `_env.py` and `_boilerplate.py` helpers — do not reimplement
env loading per file.
