"""Bootstrap a shared .env for every example in this directory.

Each example lives in ``examples/`` and reads ``os.environ[...]`` for
its API keys (``NULLRUN_API_KEY``, ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``,
``MISTRAL_API_KEY``, ``GEMINI_API_KEY``, ``COHERE_API_KEY``,
``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` / ``AWS_DEFAULT_REGION``).

The canonical source for those keys is the shared ``examples/.env``
file (copied from ``examples/.env.example`` by the developer). To
avoid sprinkling ``load_dotenv()`` / ``python-dotenv`` boilerplate
into every example, this module does the load once and is imported
at the top of every example::

    from _env import load_env  # noqa: F401

    load_env()

``load_env()`` is a no-op when ``python-dotenv`` is not installed —
the SDK examples intentionally avoid pulling in extra deps for the
"just run the example" path. The developer gets a clear hint to
``pip install python-dotenv`` if they want .env auto-loading.

Why a separate ``_env.py`` (leading underscore) and not
``nullrun_examples.env`` or similar:

  * Each example already has ``from nullrun import ...`` at the top.
    Adding another top-level import is one extra line; we don't
    need a full module hierarchy.
  * The leading underscore keeps it visually obvious that this is
    repo-local glue, not a public surface.
  * ``__pycache__`` already excludes it from git.

Example ``examples/.env`` (gitignored, copy from ``.env.example``)::

    NULLRUN_API_KEY=nr_live_...
    NULLRUN_API_URL=https://api.nullrun.io
    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
    MISTRAL_API_KEY=...
    GEMINI_API_KEY=...
    COHERE_API_KEY=...
    AWS_ACCESS_KEY_ID=...
    AWS_SECRET_ACCESS_KEY=...
    AWS_DEFAULT_REGION=us-east-1
"""
from __future__ import annotations

import os
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_EXAMPLES_DIR = _THIS_DIR  # _env.py lives in examples/
_ENV_PATH = _EXAMPLES_DIR / ".env"


def _load_via_dotenv() -> bool:
    """Try to load .env via python-dotenv. Returns True on success."""
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]
    except ImportError:
        return False
    # override=False (the default): shell env always wins over .env.
    # That matches the "CI / already exported" path — never silently
    # overwrite an explicit override.
    load_dotenv(dotenv_path=_ENV_PATH, override=False)
    return True


def load_env(verbose: bool = False) -> bool:
    """Load ``examples/.env`` into ``os.environ`` if ``python-dotenv`` is installed.

    No-op when:
      * ``python-dotenv`` is not installed (developer hasn't opted in).
      * ``examples/.env`` does not exist (developer hasn't created one).

    Args:
        verbose: When True, print a one-line summary of which keys were
            loaded (useful for debugging the "why is my key not picked
            up" path). Off by default to keep example output clean.

    Returns:
        True if a .env was loaded; False otherwise. Callers normally
        ignore the return value — the function's job is to populate
        ``os.environ`` so the subsequent ``os.environ[...]`` reads
        inside the example succeed.
    """
    if not _ENV_PATH.exists():
        if verbose:
            print(f"[nullrun-examples] no {_ENV_PATH}; skipping dotenv load")
        return False
    ok = _load_via_dotenv()
    if not ok:
        if verbose:
            print(
                f"[nullrun-examples] {_ENV_PATH} found but python-dotenv is "
                "not installed; run `pip install python-dotenv` to enable "
                "auto-loading. Falling back to current shell env."
            )
        return False
    if verbose:
        # Don't print the keys themselves — just count them.
        # Reading .env ourselves (not via dotenv) keeps the count
        # honest even if dotenv did any variable interpolation.
        count = sum(1 for _ in _ENV_PATH.read_text(encoding="utf-8").splitlines()
                    if _.strip() and not _.strip().startswith("#") and "=" in _)
        print(f"[nullrun-examples] loaded {count} entries from {_ENV_PATH}")
    return True


__all__ = ["load_env"]