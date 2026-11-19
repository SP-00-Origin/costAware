"""Phase 6: compare A–D on the same task, scripted models and fault seed.

Run: python scripts/demo_policies.py --task T01 --seed 7 --fault-rate 0.25
Change timing: --interval 2 --confidence-threshold 0.7

This is an offline wiring demo, not an LLM reliability experiment. The scripted
agent replays the reference actions without adapting or inventing confidence.
The scripted verifier notices explicit errors only. Oracle failures with faults
are valid outcomes; the command fails only for invalid inputs or runtime errors.
"""
import argparse
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent import DEFAULT_MAX_STEPS, make_llm, run_episode, save_episode
from src.agent.llm import make_verifier_llm
from src.environment.tasks import get_task
from src.policies.config import DEFAULT_INTERVAL, DEFAULT_CONFIDENCE_THRESHOLD, validate_policy_config


def run_comparison(task_id="T01", seed=7, fault_rate=0.25, policy_config=None,
                   max_steps=DEFAULT_MAX_STEPS):
    """Use fresh but identically configured models and environments for each policy."""
    settings = validate_policy_config(policy_config)
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if type(fault_rate) not in (int, float) or not 0 <= fault_rate <= 1:
        raise ValueError("fault_rate must be between 0 and 1")
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    task = get_task(task_id)
    results = {}
    for policy in "ABCD":
        agent = make_llm("scripted", task=task)
        verifier = make_verifier_llm("scripted")
        results[policy] = run_episode(
            task, agent, policy=policy, seed=seed, fault_rate=fault_rate,
            max_steps=max_steps, policy_config=settings, verifier_llm=verifier,
            model_name="scripted-reference", verifier_model_name="scripted-verifier")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", default="T01", help="one task ID")
    parser.add_argument("--seed", type=int, default=7, help="fault seed; scripted models are deterministic")
    parser.add_argument("--fault-rate", type=float, default=0.25)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="C checks agent steps 0, N, 2N, ...")
    parser.add_argument("--confidence-threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--log-dir", default=None, help="default: a new folder under logs/phase6_demo")
    args = parser.parse_args(argv)
    try:
        results = run_comparison(
            args.task, args.seed, args.fault_rate,
            {"interval": args.interval, "confidence_threshold": args.confidence_threshold}, args.max_steps)
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))

    log_dir = Path(args.log_dir) if args.log_dir else (
        Path("logs") / "phase6_demo" / datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    print("Offline A-D comparison: deterministic scripted models, no API calls.")
    print("Reference agent does not adapt; verifier notices explicit errors only. Not LLM reliability evidence.")
    print(f"Task {args.task} | fault seed {args.seed} | rate {args.fault_rate} | max steps {args.max_steps}")
    print(f"C interval {args.interval} (zero-based) | D confidence threshold {args.confidence_threshold}")
    print("Scripted action confidence is unavailable; D uses risk and observed-result checks.")
    print(f"{'Policy':<8} {'Oracle':<8} {'Steps':>5} {'Checks':>7} {'Verifier calls':>15} {'Retries':>8}")
    for policy, result in results.items():
        print(f"{policy:<8} {'PASS' if result['oracle_pass'] else 'FAIL':<8} {result['steps']:>5} "
              f"{result['verify_triggered']:>7} {result['verifier_calls']:>15} {result['recovery_attempts']:>8}")
        save_episode(result, log_dir)
        if result["error"]:
            print(f"  Runtime error: {result['error']}")
    print(f"Checks count agent actions selected for verification; verifier calls also include retry checks.")
    print(f"Logs: {log_dir}")
    return 1 if any(result["error"] for result in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
