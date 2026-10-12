"""
replay.py — Phase 3
Replay mechanism for faulted episodes.

Two kinds of replay:

1. ReplayInjector — feeds back the *exact* observations recorded in a log, keyed by
   (tool, args, occurrence). Lets you re-run an agent against precisely what an
   earlier run saw, even if the injector code later changes.

2. replay_records() — re-executes the actions of a logged trajectory on a fresh
   environment with a fresh FaultInjector(seed, rate) and reports every step where
   the true or observed result differs. An empty list proves the run is reproducible.
"""
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .injector import FaultInjector, call_key


def save_records(records: List[Dict[str, Any]], path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")


def load_records(path) -> List[Dict[str, Any]]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


class ReplayInjector:
    """Returns the observation recorded for each (tool, args, occurrence); clean result if unrecorded."""

    def __init__(self, records: List[Dict[str, Any]]):
        self._table: Dict[Tuple[str, int], Tuple[Any, Optional[str]]] = {}
        counts: Dict[str, int] = {}
        for r in records:
            if r.get("invalid_call"):
                continue
            key = call_key(r["tool"], r.get("args"))
            n = counts.get(key, 0)
            counts[key] = n + 1
            self._table[(key, n)] = (r["observed_result"], r.get("fault_injected"))
        self.reset()

    def reset(self):
        self._occurrence: Dict[str, int] = {}

    def inject(self, tool_name, args, true_result):
        key = call_key(tool_name, args)
        n = self._occurrence.get(key, 0)
        self._occurrence[key] = n + 1
        if (key, n) in self._table:
            observed, fault = self._table[(key, n)]
            return copy.deepcopy(observed), fault
        return copy.deepcopy(true_result), None


def replay_records(task, records: List[Dict[str, Any]], seed: int, fault_rate: float,
                   fault_types=None) -> List[Dict[str, Any]]:
    """Re-run logged actions with a fresh seeded injector; return per-step mismatches."""
    from ..environment.env import ProcurementEnv   # local import avoids a cycle

    env = ProcurementEnv(task, injector=FaultInjector(seed=seed, fault_rate=fault_rate,
                                                      fault_types=fault_types))
    mismatches = []
    for i, r in enumerate(records):
        new = env.call(r["tool"], r.get("args", {}), origin=r.get("origin", "agent"))
        for field in ("true_result", "observed_result", "fault_injected"):
            if json.dumps(new[field], sort_keys=True, default=str) != json.dumps(r[field], sort_keys=True, default=str):
                mismatches.append({"index": i, "tool": r["tool"], "field": field,
                                   "logged": r[field], "replayed": new[field]})
    return mismatches
