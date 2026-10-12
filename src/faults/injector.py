"""
injector.py — Phase 3
The Fault Injector wraps every simulator tool call.
The agent sees the corrupted result; the oracle always checks true state.

Reproducibility design
----------------------
A single shared random stream would make the fault on step k depend on how many
calls happened before it — so a Policy B run (extra verification re-calls)
would see a *different* fault schedule from a Policy A run of the same task and
seed. Instead every call gets its own RNG derived from

        sha256(seed | tool | canonical(args) | occurrence)

where `occurrence` counts how many times this exact (tool, args) call has been
made in the episode. Consequences:
  * same task + seed → the same agent action gets the same fault under every policy
  * re-calling the same tool (recovery) is a fresh, independent roll
  * the schedule never depends on the injector's call history

A fault that would leave the result unchanged (e.g. zeroing a result with no
numbers) is not applied; the injector tries the next fault type in its shuffled
order, and reports no fault if none applies. So `fault_injected` in the logs is
always a real, visible corruption.
"""
import copy
import hashlib
import json
import random
from typing import Any, Dict, List, Optional, Tuple

FAULT_TYPES = [
    "wrong_value",       # a numeric field is off by 10–30%
    "stale_info",        # an older view of the same record is returned
    "contradictory",     # a boolean flag is flipped (e.g. suspended → not suspended)
    "malformed_output",  # structure is lost: a truncated raw string instead of an object
    "missing_field",     # a required key is dropped
    "timeout",           # the tool does not answer (the action may still have happened!)
    "incorrect_status",  # a status string is replaced by a wrong, plausible one
    "corrupted_obs",     # a numeric field is zeroed (e.g. reserved budget shows 0)
]

# Plausible-but-wrong status for each true status (incorrect_status fault)
STATUS_CORRUPTIONS = {
    "DRAFT":            "APPROVED",
    "PENDING_APPROVAL": "APPROVED",
    "PENDING":          "APPROVED",
    "APPROVED":         "RELEASED",
    "RELEASED":         "CANCELLED",
    "CANCELLED":        "DRAFT",
    "INVALIDATED":      "APPROVED",
    "ACTIVE":           "EXPIRED",
    "EXPIRED":          "ACTIVE",
    "USED":             "ACTIVE",
    "unpaid":           "paid",
    "disputed":         "unpaid",
}

# What an *older* snapshot of a record would have shown (synthetic stale_info,
# used when this exact call has no earlier result in the episode)
STALE_STATUS = {
    "EXPIRED":          "ACTIVE",
    "RELEASED":         "APPROVED",
    "APPROVED":         "PENDING_APPROVAL",
    "PENDING_APPROVAL": "DRAFT",
    "CANCELLED":        "DRAFT",
    "INVALIDATED":      "APPROVED",
    "disputed":         "unpaid",
}
STALE_BOOLS = {"expired": False, "suspended": False}   # flags that only become True over time


def canonical_args(args: Optional[Dict[str, Any]]) -> str:
    return json.dumps(args or {}, sort_keys=True, separators=(",", ":"), default=str)


def call_key(tool: str, args: Optional[Dict[str, Any]]) -> str:
    return f"{tool}|{canonical_args(args)}"


# ─── Leaf helpers (walk nested dict/list results) ────────────────────────────

def _leaves(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _leaves(v, path + (i,))
    else:
        yield path, obj


def _dicts(obj, path=()):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from _dicts(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _dicts(v, path + (i,))


def _set(obj, path, value):
    for p in path[:-1]:
        obj = obj[p]
    obj[path[-1]] = value


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class FaultInjector:
    """
    Usage:
        injector = FaultInjector(seed=42, fault_rate=0.25)
        observed, fault_type = injector.inject("check_budget", {"budget_id": "B"}, true_result)

    fault_types: restrict to a subset (ablations). never_fault: tools that are never corrupted.
    """

    def __init__(self, seed: int = 42, fault_rate: float = 0.25,
                 fault_types: Optional[List[str]] = None, never_fault=()):
        unknown = set(fault_types or []) - set(FAULT_TYPES)
        if unknown:
            raise ValueError(f"Unknown fault types: {sorted(unknown)}")
        if not 0.0 <= fault_rate <= 1.0:
            raise ValueError("fault_rate must be in [0, 1]")
        self.seed        = seed
        self.fault_rate  = fault_rate
        self.fault_types = list(fault_types or FAULT_TYPES)
        self.never_fault = set(never_fault)
        self.reset()

    def reset(self):
        """Clear per-episode memory (call counts, stale snapshots, log)."""
        self._occurrence: Dict[str, int] = {}
        self._last_clean: Dict[str, Any] = {}
        self.log: List[Dict[str, Any]] = []

    def _rng(self, key: str, occurrence: int) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}|{key}|{occurrence}".encode()).hexdigest()
        return random.Random(int(digest[:16], 16))

    def inject(self, tool_name: str, args: Optional[Dict[str, Any]],
               true_result: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Returns (observed_result, fault_type_or_None). Never mutates true_result.
        """
        key        = call_key(tool_name, args)
        occurrence = self._occurrence.get(key, 0)
        self._occurrence[key] = occurrence + 1
        previous   = self._last_clean.get(key)
        self._last_clean[key] = copy.deepcopy(true_result)

        observed, fault = copy.deepcopy(true_result), None
        rng = self._rng(key, occurrence)
        if tool_name not in self.never_fault and rng.random() < self.fault_rate:
            order = self.fault_types[:]
            rng.shuffle(order)
            for fault_type in order:
                candidate = self._apply_fault(fault_type, tool_name, copy.deepcopy(true_result), previous, rng)
                if candidate != true_result:
                    observed, fault = candidate, fault_type
                    break

        self.log.append({"tool": tool_name, "args": copy.deepcopy(args or {}), "occurrence": occurrence,
                         "fault_type": fault, "observed": copy.deepcopy(observed)})
        return observed, fault

    # ─── Fault applicators (return the corrupted copy) ─────────────────────────

    def _apply_fault(self, fault_type: str, tool_name: str, result: Any, previous: Any,
                     rng: random.Random) -> Any:
        if fault_type == "wrong_value":
            return self._mutate_numeric(result, rng)
        if fault_type == "stale_info":
            return self._stale(result, previous, rng)
        if fault_type == "contradictory":
            return self._flip_boolean(result, rng)
        if fault_type == "malformed_output":
            raw = json.dumps(result, default=str)
            cut = max(1, int(len(raw) * rng.uniform(0.3, 0.7)))
            return {"raw": raw[:cut], "parse_error": True}
        if fault_type == "missing_field":
            return self._drop_random_key(result, rng)
        if fault_type == "timeout":
            return {"error": f"TIMEOUT: tool '{tool_name}' did not respond", "timeout": True}
        if fault_type == "incorrect_status":
            return self._corrupt_status(result, rng)
        if fault_type == "corrupted_obs":
            return self._zero_numeric(result, rng)
        raise ValueError(f"Unknown fault type {fault_type}")

    def _mutate_numeric(self, d, rng):
        paths = [(p, v) for p, v in _leaves(d) if _is_number(v) and v != 0]
        if not paths:
            return d
        path, v = rng.choice(paths)
        factor = rng.uniform(1.10, 1.30) if rng.random() < 0.5 else rng.uniform(0.70, 0.90)
        new = v * factor
        new = int(round(new)) if isinstance(v, int) else round(new, 2)
        if new == v:
            new = v + (1 if isinstance(v, int) else 1.0)
        _set(d, path, new)
        return d

    def _flip_boolean(self, d, rng):
        paths = [p for p, v in _leaves(d) if isinstance(v, bool)]
        if not paths:
            return d
        path = rng.choice(paths)
        _set(d, path, not _get(d, path))
        return d

    def _drop_random_key(self, d, rng):
        candidates = [(p, k) for p, sub in _dicts(d) for k in sub if not (p == () and len(sub) == 1)]
        if not candidates:
            return d
        path, k = rng.choice(candidates)
        del _get(d, path)[k]
        return d

    def _corrupt_status(self, d, rng):
        paths = [(p, v) for p, v in _leaves(d) if isinstance(v, str) and v in STATUS_CORRUPTIONS]
        if not paths:
            return d
        path, v = rng.choice(paths)
        _set(d, path, STATUS_CORRUPTIONS[v])
        return d

    def _zero_numeric(self, d, rng):
        paths = [p for p, v in _leaves(d) if _is_number(v) and v != 0]
        if not paths:
            return d
        path = rng.choice(paths)
        _set(d, path, 0)
        return d

    def _stale(self, d, previous, rng):
        """Prefer the genuinely older result of this same call; else synthesise an older view."""
        if previous is not None and previous != d:
            return copy.deepcopy(previous)
        for path, v in list(_leaves(d)):
            last = path[-1] if path else None
            if isinstance(v, str) and v in STALE_STATUS:
                _set(d, path, STALE_STATUS[v])
            elif isinstance(v, bool) and last in STALE_BOOLS and v != STALE_BOOLS[last]:
                _set(d, path, STALE_BOOLS[last])
        return d   # unchanged if nothing could look older → caller treats as not applicable


def _get(obj, path):
    for p in path:
        obj = obj[p]
    return obj
