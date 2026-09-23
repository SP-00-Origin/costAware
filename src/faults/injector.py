"""
injector.py — Phase 3
The Fault Injector wraps every simulator tool call.
It uses random.Random(seed) so faults are fully reproducible.
The agent sees the corrupted result; the oracle always checks true state.
"""
import random
import copy
from typing import Any, Dict, Tuple, Optional


# ─── Fault Types ──────────────────────────────────────────────────────────────

FAULT_TYPES = [
    "wrong_value",       # Mutate a numeric field
    "stale_info",        # Return a cached stale result
    "contradictory",     # Flip a boolean flag (e.g. suspended ↔ approved)
    "malformed_output",  # Return a string instead of dict, or drop structure
    "missing_field",     # Remove a required key from the result
    "timeout",           # Raise a TimeoutError
    "incorrect_status",  # Change a status string to a wrong value
    "corrupted_obs",     # Zero out a numeric field
]

# Tools that will NEVER be faulted (too dangerous for experiment validity)
NEVER_FAULT = set()  # keep empty — we want to test all tools


class FaultInjector:
    """
    Wraps simulator tool calls. On each call, rolls dice against fault_rate.
    If fault triggers, applies one of the 8 fault types to the clean result.

    Usage:
        injector = FaultInjector(seed=42, fault_rate=0.25)
        true_result, observed_result, fault_type = injector.inject("check_budget", clean_result)
    """

    def __init__(self, seed: int = 42, fault_rate: float = 0.25):
        self.rng        = random.Random(seed)
        self.fault_rate = fault_rate
        self._stale_cache: Dict[str, Any] = {}   # for stale_info fault

    def inject(
        self,
        tool_name: str,
        true_result: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Returns: (observed_result, fault_type_or_None)
        observed_result is what the agent sees.
        true_result is always preserved for oracle logging.
        """
        # Update stale cache with this clean result
        self._stale_cache[tool_name] = copy.deepcopy(true_result)

        if tool_name in NEVER_FAULT:
            return copy.deepcopy(true_result), None

        if self.rng.random() > self.fault_rate:
            return copy.deepcopy(true_result), None   # no fault this time

        fault_type = self.rng.choice(FAULT_TYPES)
        observed   = copy.deepcopy(true_result)

        try:
            observed = self._apply_fault(fault_type, tool_name, observed)
        except Exception:
            # If fault application fails (e.g. no numeric fields), return clean
            return copy.deepcopy(true_result), None

        return observed, fault_type

    # ─── Private fault applicators ────────────────────────────────────────────

    def _apply_fault(self, fault_type: str, tool_name: str, result: dict) -> Any:

        if fault_type == "wrong_value":
            return self._mutate_numeric(result)

        elif fault_type == "stale_info":
            old = self._stale_cache.get(tool_name)
            return old if old else result

        elif fault_type == "contradictory":
            return self._flip_boolean(result)

        elif fault_type == "malformed_output":
            # Return a raw string instead of a dict
            return {"raw": str(result), "parse_error": True}

        elif fault_type == "missing_field":
            return self._drop_random_key(result)

        elif fault_type == "timeout":
            raise TimeoutError(f"Tool '{tool_name}' timed out")

        elif fault_type == "incorrect_status":
            return self._corrupt_status(result)

        elif fault_type == "corrupted_obs":
            return self._zero_numeric(result)

        return result

    def _mutate_numeric(self, d: dict) -> dict:
        """Add/subtract 10–30% to the first numeric field found."""
        for k, v in d.items():
            if isinstance(v, (int, float)) and v > 0:
                factor = self.rng.uniform(1.10, 1.30)
                d[k] = round(v * factor, 2)
                break
        return d

    def _flip_boolean(self, d: dict) -> dict:
        """Flip the first boolean field found."""
        for k, v in d.items():
            if isinstance(v, bool):
                d[k] = not v
                break
        return d

    def _drop_random_key(self, d: dict) -> dict:
        """Remove a random key from the result dict."""
        if len(d) > 1:
            key = self.rng.choice(list(d.keys()))
            del d[key]
        return d

    def _corrupt_status(self, d: dict) -> dict:
        """Replace a status string with an incorrect one."""
        STATUS_CORRUPTIONS = {
            "PENDING_APPROVAL": "APPROVED",
            "APPROVED":         "PENDING_APPROVAL",
            "DRAFT":            "RELEASED",
            "ACTIVE":           "EXPIRED",
            "EXPIRED":          "ACTIVE",
            "True":             "False",
        }
        for k, v in d.items():
            if isinstance(v, str) and v in STATUS_CORRUPTIONS:
                d[k] = STATUS_CORRUPTIONS[v]
                break
        return d

    def _zero_numeric(self, d: dict) -> dict:
        """Set first numeric field to 0 (e.g. reserved budget disappears)."""
        for k, v in d.items():
            if isinstance(v, (int, float)) and v > 0:
                d[k] = 0
                break
        return d
