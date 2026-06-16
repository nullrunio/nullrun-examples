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

## Examples

| File | Framework | What it shows |
| --- | --- | --- |
| [`raw_openai_basic.py`](./examples/raw_openai_basic.py) | raw OpenAI | `@protect` on a single LLM call |
| [`openai_agents_basic.py`](./examples/openai_agents_basic.py) | OpenAI Agents SDK | `@protect` on a multi-step agent run |
| [`langgraph_basic.py`](./examples/langgraph_basic.py) | LangGraph | `NullRunCallback` inside a graph |
| [`cost_cap_demo.py`](./examples/cost_cap_demo.py) | any | Demonstrates a hard budget cap that halts the agent |

## Running

```bash
export NULLRUN_API_KEY=nr_live_...
python examples/raw_openai_basic.py
```

All examples are read-only — they do not modify the gateway state. They
will create events in your dashboard under the `examples` tag.

## Contributing

PRs welcome. Keep each example under 80 lines. No external state beyond
the NullRun API key.
