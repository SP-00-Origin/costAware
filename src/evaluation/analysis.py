"""Rebuild experiment summaries and dashboard from the recorded plan and events."""
import json
import os
from pathlib import Path
from random import Random
from statistics import mean
from urllib.parse import quote

from .dashboard import render_dashboard, render_project_dashboard
from .metrics import summarize


def read_run(path):
    episodes = {}
    header = None
    finished = False
    with Path(path).open(encoding="utf-8") as log:
        for line in log:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                if not line.endswith("\n") and header and not finished:
                    break
                raise
            event = row["event"]
            if header is None:
                if event != "run_started" or row.get("schema_version") != 1:
                    raise ValueError("Unsupported experiment log")
                header = row
                for item in row["plan"]:
                    if item["episode_id"] in episodes:
                        raise ValueError("Duplicate planned episode")
                    episodes[item["episode_id"]] = {**item, "status": "planned",
                                                    "trajectory": [], "result": {}}
                continue
            if finished:
                raise ValueError("Unexpected event after run_finished")
            if event == "run_finished":
                if any(ep["status"] in ("planned", "interrupted") for ep in episodes.values()):
                    raise ValueError("Finished run has missing episode outcomes")
                finished = True
                continue
            episode = episodes[row["episode_id"]]
            if event == "episode_started" and episode["status"] == "planned":
                episode.update(status="interrupted", goal=row["goal"])
            elif event == "step" and episode["status"] == "interrupted":
                episode["trajectory"].append(row["step"])
            elif (event == "episode_finished" and episode["status"] == "interrupted"
                  and row["status"] in ("completed", "error")):
                episode.update(status=row["status"], result=row["result"])
            else:
                raise ValueError(f"Unexpected event {event} for {row['episode_id']}")
    if header is None:
        raise ValueError("Experiment log is empty")
    return header, list(episodes.values())


def write_report(path):
    path = Path(path)
    header, episodes = read_run(path)
    summary = summarize(episodes)
    pairs = compare_to_b(episodes)
    (path.parent / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (path.parent / "paired.json").write_text(json.dumps(pairs, indent=2), encoding="utf-8")
    (path.parent / "dashboard.html").write_text(render_dashboard(header, episodes, summary, pairs),
                                                encoding="utf-8")
    return summary


def write_project_dashboard(root):
    root = Path(root)
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    runs = []
    skipped = []
    for path in find_run_logs(root):
        report = path.with_name("dashboard.html")
        if not report.is_file():
            continue
        try:
            header, episodes = read_run(path)
            config = header["config"]
            runs.append({
                "id": header["run_id"],
                "provider": config["provider"],
                "model": config["model"],
                "fault_rate": config["fault_rate"],
                "href": quote(Path(os.path.relpath(report, output)).as_posix()),
                "summary": summarize(episodes),
            })
        except (OSError, ValueError, KeyError, TypeError):
            skipped.append(path.relative_to(root).as_posix())
    dashboard = output / "dashboard.html"
    dashboard.write_text(render_project_dashboard(runs, skipped), encoding="utf-8")
    return dashboard


def find_run_logs(root):
    paths = []
    for folder in (root / "output", root / "logs"):
        for path in folder.rglob("events.jsonl"):
            if path.is_file() and path.resolve().is_relative_to(root.resolve()):
                paths.append(path)
    return sorted(paths, key=lambda path: (path.stat().st_mtime, str(path)), reverse=True)


def compare_to_b(episodes):
    """Pair completed runs by task and seed, then resample whole tasks for the interval."""
    completed = {}
    for episode in episodes:
        if episode["status"] == "completed":
            key = episode["task_id"], episode["seed"]
            completed.setdefault(episode["policy"], {})[key] = episode["result"]
    reference = completed.get("B", {})
    comparisons = {}
    for policy, outcomes in completed.items():
        if policy == "B":
            continue
        task_deltas = {}
        call_deltas = []
        for key in sorted(reference.keys() & outcomes.keys()):
            candidate, baseline = outcomes[key], reference[key]
            delta = int(candidate["oracle_pass"]) - int(baseline["oracle_pass"])
            task_deltas.setdefault(key[0], []).append(delta)
            call_deltas.append(candidate["verifier_calls"] - baseline["verifier_calls"])
        if not task_deltas:
            continue
        per_task = [mean(deltas) for deltas in task_deltas.values()]
        interval = None
        if len(per_task) >= 2:
            rng = Random(0)
            samples = sorted(mean(rng.choices(per_task, k=len(per_task))) for _ in range(2000))
            interval = [samples[49], samples[1949]]
        comparisons[policy] = dict(pairs=len(call_deltas), tasks=len(per_task),
                                   success_delta=mean(per_task), success_delta_ci95=interval,
                                   calls_delta=mean(call_deltas))
    return comparisons
