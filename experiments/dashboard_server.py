"""Serve the local CostAware research dashboard."""
import argparse
import json
import subprocess
import sys
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.analysis import find_run_logs


class Console:
    def __init__(self):
        self.lock = Lock()
        self.output = deque(maxlen=300)
        self.status = "idle"
        self.exit_code = None
        self.operation = None

    def snapshot(self):
        with self.lock:
            return dict(status=self.status, output="".join(self.output),
                        exit_code=self.exit_code, operation=self.operation)

    def start(self, operation, args):
        with self.lock:
            if self.status == "running":
                return False
            self.output.clear()
            self.output.append(subprocess.list2cmdline(["python", "-u", *args]) + "\n\n")
            self.status = "running"
            self.exit_code = None
            self.operation = operation
        Thread(target=self.run, args=(args,), daemon=True).start()
        return True

    def run(self, args):
        code = 1
        try:
            with subprocess.Popen([sys.executable, "-u", *args], cwd=ROOT, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                  errors="replace") as process:
                for line in process.stdout:
                    with self.lock:
                        self.output.append(line[:4000])
                code = process.wait()
        except OSError as exc:
            with self.lock:
                self.output.append(f"Could not start the command: {exc}\n")
        finally:
            with self.lock:
                self.status = "finished"
                self.exit_code = code


def configs():
    choices = {}
    folder = ROOT / "experiments" / "configs"
    for file in sorted(folder.glob("*.json")):
        if not file.resolve().is_relative_to(folder.resolve()):
            continue
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            choices[file.name] = {key: data.get(key) for key in ("provider", "tasks", "policies", "seeds", "fault_rate")}
        except (OSError, ValueError, AttributeError):
            continue
    return choices


def run_logs():
    return {path.relative_to(ROOT).as_posix(): path for path in find_run_logs(ROOT)}


def list_runs():
    runs = []
    for key, path in run_logs().items():
        try:
            with path.open(encoding="utf-8") as log:
                header = json.loads(log.readline())
            config = header["config"]
            runs.append(dict(key=key, id=header["run_id"], provider=config["provider"],
                             model=config["model"], episodes=len(header["plan"]),
                             ready=path.with_name("dashboard.html").is_file()))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return runs


class DashboardHandler(BaseHTTPRequestHandler):
    def send_body(self, status, body, content_type, download=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; "
                         "form-action 'self'; base-uri 'none'")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code=200):
        self.send_body(code, json.dumps(data).encode(), "application/json")

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if self.headers.get("Host") != self.origin.removeprefix("http://"):
            self.send_json({"error": "Use the printed local dashboard URL."}, 403)
            return
        url = urlsplit(self.path)
        assets = {"/": ("dashboard.html", "text/html; charset=utf-8"),
                  "/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8")}
        if url.path in assets:
            name, content_type = assets[url.path]
            self.send_body(200, (ROOT / "experiments" / "web" / name).read_bytes(), content_type)
        elif url.path == "/api/catalog":
            self.send_json({"configs": configs(), "runs": list_runs()})
        elif url.path == "/api/console":
            self.send_json(self.server.console.snapshot())
        elif url.path in ("/report", "/events"):
            key = parse_qs(url.query).get("run", [""])[0]
            log = run_logs().get(key)
            if log:
                path = log.with_name("dashboard.html") if url.path == "/report" else log
                if path.resolve().is_relative_to(ROOT.resolve()) and path.is_file():
                    if url.path == "/report":
                        self.send_body(200, path.read_bytes(), "text/html; charset=utf-8")
                    else:
                        self.send_body(200, path.read_bytes(), "application/x-ndjson", "events.jsonl")
                    return
            self.send_json({"error": "Run or report unavailable."}, 404)
        else:
            self.send_json({"error": "Unknown route."}, 404)

    def do_POST(self):
        if self.headers.get("Host") != self.origin.removeprefix("http://") or self.headers.get("Origin") != self.origin:
            self.send_json({"error": "Open the dashboard at its local URL."}, 403)
            return
        if self.path != "/api/command" or self.headers.get_content_type() != "application/json":
            self.send_json({"error": "Expected a dashboard command."}, 400)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 4096:
                raise ValueError
            request = json.loads(self.rfile.read(length))
            operation = request["operation"]
            target = request["target"]
            if not isinstance(target, str):
                raise ValueError
            args = ["experiments/run_experiment.py"]
            if operation == "run" and target in configs():
                args.extend(["--config", f"experiments/configs/{target}"])
            elif operation == "analyze" and target in run_logs():
                args.extend(["--from-log", target])
            else:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            self.send_json({"error": "Select a saved config or run from the dashboard."}, 400)
            return
        if not self.server.console.start(operation, args):
            self.send_json({"error": "A command is already running."}, 409)
            return
        self.send_json({"status": "running"}, 202)

    def log_message(self, format, *args):
        if args[1] not in ("200", "202"):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler) as server:
        server.console = Console()
        print(f"CostAware dashboard: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
