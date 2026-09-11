"""TC-27 runner — wraps concurrency probe with _wire_tracer."""
from __future__ import annotations
import json, sys, importlib.util
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
QA = EXAMPLES.parent / "qa"
PROBE = QA / "probes" / "concurrency_demo.py"
DUMP = EXAMPLES / "_tc27_wire_dump.json"

sys.path.insert(0, str(EXAMPLES))
sys.path.insert(0, str(QA / "probes"))

import _wire_tracer
_wire_tracer.install()
from _env import load_env
load_env()

spec = importlib.util.spec_from_file_location("concurrency_demo", str(PROBE))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

print("=== TC-27 PROBE START ===", flush=True)
try:
    rc = mod.main()
finally:
    captures = _wire_tracer.captured()
    DUMP.write_text(json.dumps(captures, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"=== TC-27 WIRE DUMP WRITTEN: {len(captures)} exchanges ===", flush=True)
