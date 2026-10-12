"""
run_agent.py — Phase 4
Run the LangGraph agent on one task or the whole dataset.

Examples
  # Dry run, no API key: scripted agent replays each reference solution (clean env)
  python run_agent.py --task all --provider scripted

  # Real Claude agent on clean tasks (Phase 4 exit check)
  export ANTHROPIC_API_KEY=...
  python run_agent.py --task all --provider anthropic

  # One task with faults under Policy D, showing true vs observed results
  python run_agent.py --task T08 --provider anthropic --policy D --fault-rate 0.25 --seed 3 -v

Trajectories are written to logs/<run-name>/ as one JSONL file per episode.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.agent import DEFAULT_MAX_STEPS, format_episode, make_llm, run_episode, save_episode  # noqa: E402
from src.agent.llm import DEFAULT_MODEL  # noqa: E402
from src.environment.tasks import load_tasks  # noqa: E402


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--task", default="T01", help="task id, comma-separated ids, or 'all'")
    p.add_argument("--provider", choices=["anthropic", "scripted"], default="anthropic")
    p.add_argument("--model", default=None, help=f"Claude model id (default {DEFAULT_MODEL})")
    p.add_argument("--policy", choices=list("ABCD"), default="A")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--fault-rate", type=float, default=0.0, help="0 = clean environment")
    p.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    p.add_argument("--log-dir", default=None, help="default logs/<timestamp>")
    p.add_argument("-v", "--verbose", action="store_true", help="show observed/true results per step")
    args = p.parse_args(argv)

    tasks = load_tasks()
    if args.task != "all":
        wanted = set(args.task.split(","))
        tasks = [t for t in tasks if t.id in wanted]
        missing = wanted - {t.id for t in tasks}
        if missing:
            p.error(f"unknown task id(s): {sorted(missing)}")

    log_dir = Path(args.log_dir or Path("logs") / time.strftime("run_%Y%m%d_%H%M%S"))
    model_name = "scripted-reference" if args.provider == "scripted" else (args.model or DEFAULT_MODEL)

    results = []
    for task in tasks:
        llm = make_llm(args.provider, model=args.model, task=task)
        res = run_episode(task, llm, policy=args.policy, seed=args.seed, fault_rate=args.fault_rate,
                          max_steps=args.max_steps, model_name=model_name)
        save_episode(res, log_dir)
        results.append(res)
        print(format_episode(res, show_results=args.verbose), "\n")

    n_pass = sum(r["oracle_pass"] for r in results)
    print("═" * 64)
    print(f"{'Task':<6} {'Tier':<7} {'Oracle':<8} {'Steps':>5} {'Faults':>6} {'Verify':>6}  End")
    for r in results:
        print(f"{r['task_id']:<6} {r['tier']:<7} {'PASS' if r['oracle_pass'] else 'FAIL':<8} "
              f"{r['steps']:>5} {r['faults_injected']:>6} {r['verify_triggered']:>6}  {r['done_reason']}")
    tokens = sum(r["usage"].get("input_tokens", 0) + r["usage"].get("output_tokens", 0) for r in results)
    print("═" * 64)
    print(f"{n_pass}/{len(results)} PASS | model {model_name} | policy {args.policy} | "
          f"fault rate {args.fault_rate} | tokens {tokens} | logs → {log_dir}")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
