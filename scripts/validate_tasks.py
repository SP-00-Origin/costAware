"""
Validate tasks/tasks.jsonl (Phase 2 exit criterion).

    python scripts/validate_tasks.py [path/to/tasks.jsonl]

Exit code 0 only if every task is valid.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.environment.tasks import load_tasks  # noqa: E402
from src.evaluation.validate import validate_all  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1] if len(sys.argv) > 1 else None
    tasks = load_tasks(path)
    report = validate_all(tasks)

    print(f"{'Task':<6} {'Tier':<7} {'Family':<22} {'Ref':>4} {'Neg':>4}  Result")
    print("-" * 60)
    for t in tasks:
        problems = report[t.id]
        status = "✅ valid" if not problems else "❌ " + " | ".join(problems)
        print(f"{t.id:<6} {t.tier:<7} {t.family:<22} {len(t.reference_solution):>4} "
              f"{len(t.negatives):>4}  {status}")
    tiers = Counter(t.tier for t in tasks)
    bad = [k for k, v in report.items() if v]
    print("-" * 60)
    print(f"{len(tasks)} tasks | tiers: {dict(tiers)} | families: {len({t.family for t in tasks})} "
          f"| invalid: {len(bad)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
