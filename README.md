# nullrun-examples

Working examples for the
[nullrun Python SDK](https://github.com/nullrunio/nullrun-sdk-python).

Each example is a self-contained, runnable file. The intent is to show the
smallest possible change to add enforcement to a common agent framework.

## Prerequisites

```bash
pip install nullrun
export NULLRUN_API_KEY=nr_live_...
```

Get an API key from the [NullRun dashboard](https://app.nullrun.io).

## Auto-instrumentation

`nullrun.init(api_key=...)` patches the underlying HTTP transport and any
imported agent framework (`openai`, `openai-agents`, `langgraph`,
`autogen`, …) automatically. You get cost tracking without changing your
call sites; `@protect` is the **gate** layer (budget / kill / pause) that
runs *before* the call.

For frameworks that ship an extra, install with the matching optional
dependency (`nullrun[langgraph]`, `nullrun[openai]`, `nullrun[llama-index]`,
`nullrun[crewai]`, `nullrun[autogen]`, etc.). The `openai-agents` SDK is
auto-detected at runtime without a separate extra.

## Examples

| File | Framework | What it shows |
| --- | --- | --- |
| [`raw_openai_basic.py`](./examples/raw_openai_basic.py) | raw OpenAI | `@protect` + `@guarded` on a single LLM call |
| [`openai_agents_basic.py`](./examples/openai_agents_basic.py) | OpenAI Agents SDK | `@protect` + `@guarded` on a multi-step agent run |
| [`langgraph_basic.py`](./examples/langgraph_basic.py) | LangGraph | Auto-instrumented `StateGraph` (recommended) |
| [`langgraph_manual_wrapper.py`](./examples/langgraph_manual_wrapper.py) | LangGraph | `nullrun.toolbox.langgraph.wrapper` for re-compiled graphs |
| [`cost_cap_demo.py`](./examples/cost_cap_demo.py) | any | Hard budget cap that halts the agent |

## Running

```bash
export NULLRUN_API_KEY=nr_live_...
python examples/raw_openai_basic.py
```

All examples are read-only — they do not modify org state, policies, or
keys on your account. They **do** emit `track` events to the gateway
(auto-instrumented HTTP traffic from `init()`), so a `cost_attribution`
or `examples` tag in the dashboard will pick them up.

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

## Contributing

PRs welcome. Keep each example under 80 lines. No external state beyond
the NullRun API key.