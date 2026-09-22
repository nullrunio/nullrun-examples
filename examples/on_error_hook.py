"""Wire a custom error hook for observability (``nullrun.on_error``).

The hook fires BEFORE every ``NullRunError`` raise with the
structured fields the catalog carries (``error_code``,
``retryable``, ``user_action``, ``docs_url``, ``stage``,
``workflow_id``). Pair it with ``with nullrun.handle():`` so each
hook fires once on failure, and the script still exits cleanly
with the four-line developer report.

This is the recommended integration point for Sentry / dashboards /
PagerDuty — the catalog fields are stable, machine-readable, and
already cover the "what does this error mean + what should the user
do" surface so you don't have to grep docs to build the mapping.

Run:
    pip install "nullrun" openai
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
from nullrun import protect, shutdown

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nullrun.example")


@nullrun.on_error
def _to_log(err, ctx):
    # `err` is a NullRunError subclass; `ctx` is an ErrorContext.
    # Both are documented in nullrun.observability.error_hooks.
    # The `extra` keys below are deliberately namespaced to avoid clashing
    # with reserved `LogRecord` attribute names (`message`, `asctime`,
    # `levelname`, ...). If you add a custom key here, double-check against
    # the LogRecord spec at https://docs.python.org/3/library/logging.html#logrecord-attributes.
    log.warning(
        "NullRun error code=%s stage=%s retryable=%s workflow_id=%s",
        err.error_code, ctx.stage, err.retryable, ctx.workflow_id,
        extra={
            "nr_code": err.error_code,
            "nr_stage": ctx.stage,
            "nr_retryable": err.retryable,
            "nr_workflow_id": ctx.workflow_id,
            "nr_user_action": err.user_action,
        },
    )


client = OpenAI()


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
        with nullrun.handle():
            print(answer("In one sentence, what does NullRun do?"))
    finally:
        shutdown()