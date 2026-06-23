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
| [`raw_openai_basic.py`](./examples/raw_openai_basic.py) | raw OpenAI | `@protect` on a single LLM call |
| [`openai_agents_basic.py`](./examples/openai_agents_basic.py) | OpenAI Agents SDK | `@protect` on a multi-step agent run |
| [`langgraph_basic.py`](./examples/langgraph_basic.py) | LangGraph | Auto-instrumented `StateGraph` |
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

## Contributing

PRs welcome. Keep each example under 80 lines. No external state beyond
the NullRun API key.
