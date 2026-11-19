"""Run a matched experiment or rebuild artifacts from its JSONL log."""
import argparse
import itertools
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.graph import run_episode
from src.agent.llm import DEFAULT_MODELS, default_model, make_llm, make_verifier_llm
from src.environment.tasks import get_task, load_tasks
from src.evaluation.analysis import write_project_dashboard, write_report
from src.policies.config import validate_policy_config
from src.provider_errors import error_details, public_error


def load_config(path):
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {"provider", "tasks", "policies", "seeds", "fault_rate", "max_steps"}
    allowed = required | {"model", "verifier_model", "policy_config", "phase"}
    if not isinstance(config, dict) or not required <= config.keys() or config.keys() - allowed:
        raise ValueError("Invalid config fields")
    for key in ("tasks", "policies", "seeds"):
        if not isinstance(config[key], list) or not config[key]:
            raise ValueError(f"{key} must be a nonempty list")
        for value in config[key]:
            if type(value) is not (int if key == "seeds" else str) or not str(value).strip():
                raise ValueError(f"Invalid value in {key}")
        if len(set(config[key])) != len(config[key]):
            raise ValueError(f"Duplicate values in {key}")
    if config["tasks"] == ["all"]:
        config["tasks"] = [task.id for task in load_tasks()]
    for task_id in config["tasks"]:
        get_task(task_id)
    provider = config["provider"]
    if not isinstance(provider, str) or provider not in DEFAULT_MODELS:
        raise ValueError("Unknown provider")
    if set(config["policies"]) - set("ABCD"):
        raise ValueError("Policies must be A, B, C or D")
    if type(config["fault_rate"]) not in (int, float) or not 0 <= config["fault_rate"] <= 1:
        raise ValueError("fault_rate must be between 0 and 1")
    if type(config["max_steps"]) is not int or config["max_steps"] < 1:
        raise ValueError("max_steps must be a positive integer")
    config.setdefault("phase", 7)
    if type(config["phase"]) is not int or config["phase"] < 1:
        raise ValueError("phase must be a positive integer")
    for key in ("model", "verifier_model"):
        if key in config and (not isinstance(config[key], str) or not config[key].strip()):
            raise ValueError(f"{key} must be a nonempty string")
    config["model"] = config.get("model") or default_model(provider)
    config["verifier_model"] = config.get("verifier_model") or config["model"]
    if provider == "scripted":
        config["model"] = "scripted-reference"
        config["verifier_model"] = "scripted-verifier"
    config["policy_config"] = validate_policy_config(config.get("policy_config"))
    return config


def append_event(log, event, **fields):
    log.write(json.dumps({"event": event, **fields}, allow_nan=False) + "\n")
    log.flush()


def run_batch(config, directory, run_id, progress=None):
    directory.mkdir(parents=True, exist_ok=False)
    log_path = directory / "events.jsonl"
    plan = []
    for task_id, (trial, seed), policy in itertools.product(
        config["tasks"], enumerate(config["seeds"], 1), config["policies"]
    ):
        plan.append(dict(episode_id=f"episode-{len(plan) + 1:04}", task_id=task_id,
                         trial=trial, seed=seed, policy=policy))
    provider = config["provider"]
    with log_path.open("x", encoding="utf-8") as log:
        append_event(log, "run_started", schema_version=1, run_id=run_id, config=config, plan=plan)
        for index, item in enumerate(plan, 1):
            episode_id = item["episode_id"]
            task = get_task(item["task_id"])
            policy = item["policy"]
            append_event(log, "episode_started", episode_id=episode_id, goal=task.goal)
            label = f"{index}/{len(plan)}  {task.id}  policy {policy}  seed {item['seed']}"
            if progress:
                progress(f"{label}  running")
            try:
                agent = make_llm(provider, model=config["model"], task=task)
                verifier = None if policy == "A" else make_verifier_llm(provider, config["verifier_model"])
                result = run_episode(task, agent, policy=policy, seed=item["seed"],
                                     fault_rate=config["fault_rate"], max_steps=config["max_steps"],
                                     policy_config=config["policy_config"], verifier_llm=verifier,
                                     model_name=config["model"],
                                     verifier_model_name=config["verifier_model"] if verifier else "")
            except Exception as exc:
                details = error_details(exc)
                failure = {"error": public_error(type(exc).__name__, details)}
                if details:
                    failure["error_details"] = details
                append_event(log, "episode_finished", episode_id=episode_id, status="error",
                             result=failure)
                if progress:
                    progress(f"{label}  ERROR  {failure['error']}")
                continue
            for step in result.pop("trajectory"):
                if step.get("verifier_error"):
                    step["verifier_error"] = public_error(step["verifier_error"].split(":", 1)[0],
                                                          step.get("verifier_error_details"))
                append_event(log, "step", episode_id=episode_id, step=step)
            status = "error" if result.get("error") else "completed"
            if status == "error":
                result["error"] = public_error(result["error"].split(":", 1)[0],
                                               result.get("error_details"))
            append_event(log, "episode_finished", episode_id=episode_id, status=status, result=result)
            if progress:
                outcome = f"ERROR {result['error']}" if status == "error" else "PASS" if result["oracle_pass"] else "FAIL"
                progress(f"{label}  {outcome}  selected {result['verify_triggered']}  "
                         f"verifier calls {result['verifier_calls']}")
        append_event(log, "run_finished")
    return log_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--config", type=Path)
    source.add_argument("--from-log", type=Path)
    source.add_argument("--dashboard", action="store_true", help="Rebuild the project dashboard")
    parser.add_argument("--output-root", type=Path, default=ROOT / "output" / "experiments")
    args = parser.parse_args()
    try:
        if args.dashboard:
            print(f"Project dashboard: {write_project_dashboard(ROOT)}")
            return 0
        if args.config:
            load_dotenv(ROOT / ".env")
            run_id = uuid4().hex
            log = run_batch(load_config(args.config), args.output_root / run_id, run_id,
                            progress=lambda line: print(line, flush=True))
        else:
            log = args.from_log
        summary = write_report(log)
        dashboard = write_project_dashboard(ROOT)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Experiment error: {exc}\n")
    print(f"Log: {log}\nRun dashboard: {log.parent / 'dashboard.html'}\nProject dashboard: {dashboard}")
    return int(any(row["completed"] != row["planned"] for row in summary.values()))


if __name__ == "__main__":
    sys.exit(main())
