"""
run_simulation.py — Quick Start Demo (no LLM, no API key)
Shows the deterministic pipeline end to end on the hand-written task set:

    Task → Simulator → Fault Injector → Policy → Oracle → Log

The "agent" here is the task's reference solution, replayed open-loop: it never
reacts to what it observes. That makes this a check of the environment, faults and
oracle — not of an agent. For the real agent use run_agent.py.

Usage:
    python run_simulation.py                    # T01, all four policies, seed 42, rate 0.25
    python run_simulation.py --task T17 --rate 0.4
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.environment.env import ProcurementEnv   # noqa: E402
from src.environment.tasks import get_task       # noqa: E402
from src.evaluation.oracle import oracle_check   # noqa: E402
from src.faults.injector import FaultInjector    # noqa: E402
from src.policies.policies import should_verify  # noqa: E402


def run_experiment(task_id: str = "T01", policy: str = "D", fault_seed: int = 42, fault_rate: float = 0.25):
    task = get_task(task_id)
    print(f"\n{'=' * 64}\n  {task.id} ({task.tier}, {task.family}) | Policy={policy} | "
          f"Seed={fault_seed} | Rate={fault_rate}\n{'=' * 64}")

    env = ProcurementEnv(task, injector=FaultInjector(seed=fault_seed, fault_rate=fault_rate))
    trajectory = []
    for action in task.reference_solution:
        r = env.call(action["tool"], action["args"])
        verify, reason = should_verify(policy=policy, action={"tool": r["tool"], "args": r["args"]},
                                       result=r["observed_result"], history=trajectory, step=r["step"])
        r.update(verify_triggered=verify, trigger_reason=reason)
        trajectory.append(r)

    oracle_pass, diff = oracle_check(env.true_state, task.expected_final_state, env.sim.initial_state)

    print(f"{'Step':<5} {'Tool':<24} {'Fault':<18} {'Verify':<7} Reason")
    print("─" * 64)
    for s in trajectory:
        print(f"{s['step']:<5} {s['tool']:<24} {(s['fault_injected'] or '—'):<18} "
              f"{'YES ✓' if s['verify_triggered'] else 'no':<7} {s['trigger_reason']}")
    print("─" * 64)
    print(f"  ORACLE: {'✅ PASS' if oracle_pass else '❌ FAIL'}")
    for check, detail in diff.items():
        print(f"  {'✅' if detail['pass'] else '❌'} {check:<32} expected={detail['expected']}  "
              f"actual={detail['actual']}")
    n_verify = sum(s["verify_triggered"] for s in trajectory)
    print(f"\n  Verification overhead: {n_verify}/{len(trajectory)} steps")
    return oracle_pass, trajectory


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="T01")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rate", type=float, default=0.25)
    a = ap.parse_args()

    results = {}
    for policy in "ABCD":
        passed, traj = run_experiment(a.task, policy=policy, fault_seed=a.seed, fault_rate=a.rate)
        results[policy] = (passed, sum(s["verify_triggered"] for s in traj), len(traj))

    print(f"\n{'=' * 44}\n  SUMMARY — {a.task}\n{'=' * 44}")
    print(f"  {'Policy':<8} {'Oracle':<9} {'Verified':>8}")
    for p, (ok, v, n) in results.items():
        print(f"  {p:<8} {'PASS ✅' if ok else 'FAIL ❌':<9} {v:>4}/{n}")
    print("  (Open-loop replay: verification is logged but not acted on until Phase 5.)")
