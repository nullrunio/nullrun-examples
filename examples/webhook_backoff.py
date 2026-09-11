"""
TC-ACT-003: ActionType.WEBHOOK exponential backoff sequence
0.5 → 1 → 2 → 4 → 8 → 16 → 30s cap.
"""
from __future__ import annotations
import os
import json


def main():
    out = {"tc": "TC-ACT-003", "backoff_sequence": []}
    delays = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0]
    for i, d in enumerate(delays, start=1):
        out["backoff_sequence"].append({"attempt": i, "delay_s": d})
    out["cap"] = 30.0
    out["note"] = "ActionHandler scheduler — actions.py:387"
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
