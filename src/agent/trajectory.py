"""
trajectory.py — Phase 4
Write / read / pretty-print episode trajectories so every run is inspectable.

One JSONL file per episode:
  {"type": "step", ...step record (true + observed result, fault, policy decision)...}
  ...
  {"type": "summary", ...episode summary (oracle verdict, done reason, usage)...}
"""
import json
from pathlib import Path
from typing import Any, Dict, List


def episode_filename(result: Dict[str, Any]) -> str:
    rate = str(result["fault_rate"]).replace(".", "p")
    return f"{result['task_id']}_policy{result['policy']}_seed{result['seed']}_rate{rate}.jsonl"


def save_episode(result: Dict[str, Any], log_dir) -> Path:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / episode_filename(result)
    with open(path, "w") as f:
        for r in result["trajectory"]:
            f.write(json.dumps({"type": "step", **r}, default=str) + "\n")
        summary = {k: v for k, v in result.items() if k != "trajectory"}
        f.write(json.dumps({"type": "summary", **summary}, default=str) + "\n")
    return path


def load_episode(path) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            kind = row.pop("type")
            if kind == "step":
                steps.append(row)
            else:
                summary = row
    return {**summary, "trajectory": steps}


def _short(obj: Any, n: int = 60) -> str:
    s = json.dumps(obj, default=str, separators=(",", ":"))
    return s if len(s) <= n else s[: n - 1] + "…"


def format_episode(result: Dict[str, Any], show_results: bool = False) -> str:
    lines = [f"── {result['task_id']} | policy {result['policy']} | seed {result['seed']} | "
             f"fault rate {result['fault_rate']} | model {result.get('model') or '-'}",
             f"{'#':>3} {'Tool':<23} {'Args':<36} {'Fault':<17} {'Verify':<6} Reason"]
    for i, r in enumerate(result["trajectory"]):
        verify = "YES" if r.get("verify_decision") else "no"
        lines.append(f"{i:>3} {r['tool']:<23} {_short(r['args'], 36):<36} "
                     f"{(r.get('fault_injected') or '—'):<17} {verify:<6} {r.get('trigger_reason', '')}")
        if show_results:
            lines.append(f"      observed: {_short(r['observed_result'], 110)}")
            if r.get("fault_injected"):
                lines.append(f"      true:     {_short(r['true_result'], 110)}")
    verdict = "PASS ✅" if result["oracle_pass"] else "FAIL ❌"
    lines.append(f"    end: {result['done_reason']} after {result['steps']} steps | "
                 f"faults {result['faults_injected']} | verify {result['verify_triggered']} | ORACLE {verdict}")
    if not result["oracle_pass"]:
        failed = {k: v for k, v in result["oracle_diff"].items() if not v["pass"]}
        for k, v in failed.items():
            lines.append(f"      ✗ {k}: expected {_short(v['expected'], 50)} got {_short(v['actual'], 50)}")
    if result.get("error"):
        lines.append(f"    error: {result['error']}")
    return "\n".join(lines)
