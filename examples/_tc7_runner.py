"""TC-7 runner — wraps cancel_demo probe with _wire_tracer + dump file."""
from __future__ import annotations

import json
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
QA = EXAMPLES.parent / "qa"
PROBE_SCRIPT = QA / "probes" / "cancel_demo.py"
DUMP_OUT = EXAMPLES / "_tc7_wire_dump.json"

sys.path.insert(0, str(EXAMPLES))
sys.path.insert(0, str(QA / "probes"))

import _wire_tracer
_wire_tracer.install()

from _env import load_env
load_env()

import importlib.util
spec = importlib.util.spec_from_file_location("cancel_demo", str(PROBE_SCRIPT))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

print("=== TC-7 PROBE START ===", flush=True)
try:
    rc = mod.main()
    print(f"=== TC-7 PROBE END rc={rc} ===", flush=True)
except Exception as e:
    print(f"=== TC-7 PROBE END Exception={type(e).__name__}: {e} ===", flush=True)

captures = _wire_tracer.captured()
DUMP_OUT.write_text(
    json.dumps(captures, indent=2, sort_keys=True, default=str),
    encoding="utf-8",
)
print(f"=== TC-7 WIRE DUMP WRITTEN: {len(captures)} exchanges ===", flush=True)
