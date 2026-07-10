"""Wire a custom error hook for observability (``nullrun.on_error``).

The hook fires BEFORE every ``NullRunError`` raise with the
structured fields the catalog carries (``error_code``,
``retryable``, ``user_action``, ``docs_url``, ``stage``,
``workflow_id``). Pair it with ``@guarded`` so each hook fires once
on failure, and the script still exits cleanly.

This is the recommended integration point for Sentry / dashboards /
PagerDuty — the catalog fields are stable, machine-readable, and
already cover the "what does this error mean + what should the user
do" surface so you don't have to grep docs to build the mapping.

Run:
    pip install "nullrun[openai]" openai
    export NULLRUN_API_KEY=nr_live_...
    export OPENAI_API_KEY=sk-...
    python examples/on_error_hook.py
"""
from __future__ import annotations

from _env import load_env

load_env()  # populate os.environ from examples/.env (no-op if absent)


import logging
import os

from openai import OpenAI

import nullrun
from nullrun import guarded, init_or_die, protect, shutdown

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nullrun.example")


@nullrun.on_error
def _to_log(err, ctx):
    # `err` is a NullRunError subclass; `ctx` is an ErrorContext.
    # Both are documented in nullrun.observability.error_hooks.
    log.warning(
        "NullRun error",
        extra={
            "code": err.error_code,
            "stage": ctx.stage,
            "retryable": err.retryable,
            "workflow_id": ctx.workflow_id,
            "user_action": err.user_action,
        },
    )


init_or_die(api_key=os.environ["NULLRUN_API_KEY"])
client = OpenAI()


@guarded
@protect
def answer(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    try:
        # Force a known error path by setting a budget-capped policy
        # on the dashboard first -- otherwise this example succeeds
        # and the hook never fires.
        print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()