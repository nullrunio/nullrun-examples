"""TC-6 runner — wraps the chain_lifecycle_demo probe with _wire_tracer.

Subprocessed by qa/tc_6_chain.py. Reads NULLRUN_API_KEY from .env.
Imports the probe's main() directly (avoiding runpy which has
sys.exit quirks), then dumps captured wire exchanges to a file.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
QA = EXAMPLES.parent / "qa"
PROBE_SCRIPT = QA / "probes" / "chain_lifecycle_demo.py"
DUMP_OUT = EXAMPLES / "_tc6_wire_dump.json"

sys.path.insert(0, str(EXAMPLES))
sys.path.insert(0, str(QA / "probes"))

import _wire_tracer
_wire_tracer.install()

from _env import load_env
load_env()

# Import probe as module instead of runpy to avoid sys.exit() quirks.
import importlib.util
spec = importlib.util.spec_from_file_location("chain_lifecycle_demo", str(PROBE_SCRIPT))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

print("=== TC-6 PROBE START ===", flush=True)
try:
    rc = mod.main()
    print(f"=== TC-6 PROBE END rc={rc} ===", flush=True)
except SystemExit as e:
    print(f"=== TC-6 PROBE END SystemExit={e} ===", flush=True)
except Exception as e:
    print(f"=== TC-6 PROBE END Exception={type(e).__name__}: {e} ===", flush=True)
    traceback.print_exc()

# Dump captured exchanges to file.
captures = _wire_tracer.captured()
DUMP_OUT.write_text(
    json.dumps(captures, indent=2, sort_keys=True, default=str),
    encoding="utf-8",
)
print(f"=== TC-6 WIRE DUMP WRITTEN: {len(captures)} exchanges ===", flush=True)
