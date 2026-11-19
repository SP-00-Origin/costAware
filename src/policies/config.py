"""Settings for the Section 10 A–D policy baseline."""
import math

DEFAULT_INTERVAL = 3
DEFAULT_CONFIDENCE_THRESHOLD = 0.6


def validate_policy_config(config=None):
    """Return a fresh settings dict, rejecting invalid or misspelled settings."""
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("policy config must be a dict")
    unknown = set(config) - {"interval", "confidence_threshold"}
    if unknown:
        raise ValueError("unknown policy config setting")

    interval = config.get("interval", DEFAULT_INTERVAL)
    threshold = config.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
    if type(interval) is not int or interval < 1:
        raise ValueError("interval must be a positive integer")
    if (type(threshold) not in (int, float) or not 0 <= threshold <= 1
            or not math.isfinite(threshold)):
        raise ValueError("confidence_threshold must be a finite number between 0 and 1")
    return {"interval": interval, "confidence_threshold": float(threshold)}
