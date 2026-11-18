"""Phase 5: one real retry, with the same rules under every policy."""


def retry_action(env, record):
    """Repeat the action through the normal simulator and seeded fault injector.

    Writes are not rolled back or deduplicated. Both attempts remain in the log.
    """
    retry = env.call(record["tool"], record["args"], origin="recovery")
    retry.update(recovery_of=record["step"], verify_decision=True,
                 trigger_reason="recovery_recheck", verifier_verdict=None,
                 recovery_attempts=0, final_result_used=retry["observed_result"])
    return retry
