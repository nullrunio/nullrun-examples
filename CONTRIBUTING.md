# Contributing

Thanks for adding to `nullrun-examples`! This repo is the canonical
"how do I add NullRun to my stack" surface for the Python SDK. The bar
is **readability for a first-time reader**, not coverage of every edge
case.

## Layout

```
examples/
├── _env.py            # shared .env loader (do not edit per example)
├── _boilerplate.py    # shared example_run() context manager
├── <vendor>_basic.py  # one per vendor / framework (≤ 80 lines)
├── *_demo.py          # longer demos (LangGraph, MCP, approval rules)
├── probe_*.py         # QA probes — not for end-users, see qa/probes/
└── ar_*.py            # approval-rule probes — see qa/approval_rules/
qa/
├── probes/            # QA probes (not shipped in README)
└── approval_rules/    # approval-rule test scripts
tools/
└── synthetic_sdk_load.py
```

## Adding a new example

1. Create `examples/<vendor>_basic.py`.
2. Top of file — a short docstring (3–8 lines) explaining *what* the
   example shows. Include a `Run:` block with the exact `pip install`
   and `export` commands a user needs.
3. Then the body — keep it under **80 lines**. If you need more, it's a
   demo, not a basic example. Move it to `examples/<name>_demo.py` and
   add a row to the demos table in `README.md`.
4. Use the shared helpers — do **not** reimplement env loading:
   ```python
   from _env import load_env
   load_env()
   ```
   If you also want init + shutdown folded in:
   ```python
   from _boilerplate import example_run
   with example_run():
       ...
   ```
5. End every example with `shutdown()` in a `finally` block (the
   context manager above does this for you).
6. Update `README.md` and (if it's a demo) `examples/INDEX.md` to list
   the new file.

## Style

* `from __future__ import annotations` at the top.
* Imports in three groups: stdlib, third-party, `nullrun.*`. One blank
  line between groups.
* No dead `import os` — only import what you actually reference.
* `init_or_die()` without explicit `api_key=` — read it from the env
  via `_env.load_env()` so the example works with the shared `.env`.
* Don't catch `NullRunError` manually. Use `@guarded` or
  `with nullrun.handle():` for clean error translation. Reserve bare
  `except` blocks for probes that need to count allow/block outcomes.
* No hardcoded absolute filesystem paths — drive them off
  `__file__` or env vars (`PROBE_LOG_PATH` etc.).

## Tests

There is no test suite — examples are exercised by humans running them
against a real API key. CI runs `smoke_test.py` against the public
NullRun control plane to catch SDK breakage.

## Commit hygiene

* `feat(examples): ...` for new examples.
* `fix(examples): ...` for fixes.
* `docs(examples): ...` for README / doc changes only.
* Never commit `examples/.env`, `.env.backup`, `*.tmp_*.py`, or
  `__pycache__/`. The `.gitignore` already excludes them; do not
  force-add.
