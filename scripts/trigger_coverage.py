"""
trigger_coverage.py — LLM-free analysis of verification-trigger coverage.

Replays every task's reference solution open-loop under seeded fault injection and
measures, per fault type, how often each policy would trigger verification on the
faulted step. Policy D's triggers are split into
    - tool-based  (high_risk_tool): fires on the tool name, whatever the result says
    - content-based (schema_fail / low_confidence): fires because of the observed result
so we can see which faults D can actually *notice* versus catch by coincidence.

Usage:
    python scripts/trigger_coverage.py                    # 50 seeds, rate 0.25
    python scripts/trigger_coverage.py --seeds 100 --rate 0.4 --json results/tables/coverage.json
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.environment.env import ProcurementEnv     # noqa: E402
from src.environment.tasks import load_tasks       # noqa: E402
from src.faults.injector import FAULT_TYPES, FaultInjector  # noqa: E402
from src.policies.policies import should_verify    # noqa: E402

POLICIES = "ABCD"
CONTENT_TRIGGERS = {"schema_fail", "low_confidence"}


def run(seeds: int, rate: float):
    steps = 0
    faulted = defaultdict(int)                           # fault type -> faulted steps
    hit = defaultdict(lambda: defaultdict(int))          # policy -> fault -> verified faulted steps
    content_hit = defaultdict(int)                       # fault -> D content-trigger hits
    verified = defaultdict(int)                          # policy -> verified steps (all)
    false_alarm = defaultdict(int)                       # policy -> verified clean steps

    for task in load_tasks():
        for seed in range(seeds):
            env = ProcurementEnv(task, injector=FaultInjector(seed=seed, fault_rate=rate))
            history = []
            for rec in env.run_actions(task.reference_solution):
                steps += 1
                fault = rec["fault_injected"]
                if fault:
                    faulted[fault] += 1
                for p in POLICIES:
                    v, reason = should_verify(policy=p, action={"tool": rec["tool"], "args": rec["args"]},
                                              result=rec["observed_result"], history=history, step=rec["step"])
                    verified[p] += v
                    if fault and v:
                        hit[p][fault] += 1
                        if p == "D" and reason in CONTENT_TRIGGERS:
                            content_hit[fault] += 1
                    if not fault and v:
                        false_alarm[p] += 1
                history.append(rec)

    n_faulted = sum(faulted.values())
    return {
        "seeds": seeds, "rate": rate, "steps": steps, "faulted_steps": n_faulted,
        "effective_fault_rate": n_faulted / steps,
        "verify_rate": {p: verified[p] / steps for p in POLICIES},
        "fault_recall": {p: sum(hit[p].values()) / n_faulted for p in POLICIES},
        "clean_verify_rate": {p: false_alarm[p] / (steps - n_faulted) for p in POLICIES},
        "per_fault": {
            f: {"count": faulted[f],
                **{f"recall_{p}": hit[p][f] / faulted[f] for p in POLICIES if faulted[f]},
                "content_recall_D": content_hit[f] / faulted[f] if faulted[f] else None}
            for f in FAULT_TYPES
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--rate", type=float, default=0.25)
    ap.add_argument("--json", help="also write results to this path")
    a = ap.parse_args()

    r = run(a.seeds, a.rate)
    print(f"{len(load_tasks())} tasks x {r['seeds']} seeds, rate={r['rate']}: "
          f"{r['steps']} steps, {r['faulted_steps']} faulted ({r['effective_fault_rate']:.1%})\n")
    print(f"{'Policy':<8}{'verify rate':>12}{'fault recall':>14}{'clean verify':>14}")
    for p in POLICIES:
        print(f"{p:<8}{r['verify_rate'][p]:>12.1%}{r['fault_recall'][p]:>14.1%}{r['clean_verify_rate'][p]:>14.1%}")
    print(f"\n{'Fault':<18}{'n':>6}" + "".join(f"{'rec ' + p:>9}" for p in POLICIES) + f"{'D content':>11}")
    for f, d in r["per_fault"].items():
        if not d["count"]:
            continue
        print(f"{f:<18}{d['count']:>6}" + "".join(f"{d['recall_' + p]:>9.1%}" for p in POLICIES)
              + f"{d['content_recall_D']:>11.1%}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(r, indent=2))
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
