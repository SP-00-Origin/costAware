const get = (id) => document.getElementById(id);
const configSelect = get("config");
const runSelect = get("run");
const report = get("report");
const consoleOutput = get("console");
let catalog = {configs: {}, runs: []};
let status = "idle";
let submitting = false;
let observer;

async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Dashboard request failed.");
  return data;
}

function notice(message = "") {
  get("notice").textContent = message;
  get("notice").hidden = !message;
}

function showView(view) {
  get("results").hidden = view !== "results";
  get("results-button").setAttribute("aria-pressed", view === "results");
  consoleOutput.hidden = view !== "console";
  get("console-button").setAttribute("aria-pressed", view === "console");
}

function refreshControls() {
  const busy = status === "running" || submitting;
  get("start").disabled = busy || !configSelect.value;
  get("analyze").disabled = busy || !runSelect.value;
  configSelect.disabled = !configSelect.options.length;
  runSelect.disabled = !runSelect.options.length;
}

function showConfig() {
  const config = catalog.configs[configSelect.value];
  if (!config) {
    get("config-info").textContent = "No saved configs found.";
  } else {
    const mode = config.provider === "scripted" ? "Offline scripted" : config.provider;
    const policies = config.policies?.join(", ") || "—";
    const tasks = config.tasks?.join(", ") || "—";
    get("config-info").textContent = `${mode} · policies ${policies} · tasks ${tasks}`;
  }
  refreshControls();
}

function showRun(force = false) {
  const run = catalog.runs.find((item) => item.key === runSelect.value);
  const query = run ? new URLSearchParams({run: run.key}).toString() : "";
  get("run-info").textContent = run ? `${run.model} · ${run.episodes} planned episodes` : "No saved runs.";
  get("download").hidden = !run;
  if (run) get("download").href = `/events?${query}`;
  report.hidden = !run?.ready;
  get("empty").hidden = Boolean(run?.ready);
  get("empty").textContent = run ? "Rebuild analysis to generate the metrics and charts for this run."
    : "Run an experiment or select a saved run to view results.";
  if (run?.ready) {
    const url = `/report?${query}`;
    if (force || report.getAttribute("src") !== url) report.src = url;
  }
  refreshControls();
}

async function loadCatalog(preferLatest = false, reloadReport = false) {
  const oldConfig = configSelect.value;
  const oldRun = runSelect.value;
  catalog = await request("/api/catalog");
  configSelect.replaceChildren(...Object.keys(catalog.configs).map((key) => new Option(key, key)));
  if (oldConfig in catalog.configs) configSelect.value = oldConfig;
  runSelect.replaceChildren(...catalog.runs.map((run) => {
    const label = run.provider === "scripted" ? "Scripted" : run.provider;
    return new Option(`${label} · ${run.id.slice(0, 10)}`, run.key);
  }));
  if (!preferLatest && catalog.runs.some((run) => run.key === oldRun)) runSelect.value = oldRun;
  showConfig();
  showRun(reloadReport);
}

async function poll() {
  try {
    const previous = status;
    const job = await request("/api/console");
    status = job.status;
    get("status").textContent = status === "running" ? "Running…" : status === "idle" ? "Ready"
      : job.exit_code === 0 ? "Command finished" : `Command exited with code ${job.exit_code}`;
    const atEnd = consoleOutput.scrollHeight - consoleOutput.scrollTop - consoleOutput.clientHeight < 28;
    if (job.output && consoleOutput.textContent !== job.output) {
      consoleOutput.textContent = job.output;
      if (atEnd) consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }
    refreshControls();
    if (previous === "running" && status === "finished") {
      await loadCatalog(job.operation === "run", true);
    }
  } catch (error) {
    notice(error.message);
  } finally {
    setTimeout(poll, status === "running" ? 450 : 1600);
  }
}

async function launch(operation, target) {
  if (!target || submitting || status === "running") return;
  if (operation === "run" && catalog.configs[target]?.provider !== "scripted"
      && !confirm("Run this configuration with the live model provider? API usage may be billed.")) return;
  submitting = true;
  refreshControls();
  notice();
  try {
    await request("/api/command", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({operation, target}),
    });
    status = "running";
    get("status").textContent = "Running…";
    consoleOutput.textContent = "Starting command…";
    showView("console");
  } catch (error) {
    notice(error.message);
  } finally {
    submitting = false;
    refreshControls();
  }
}

get("experiment").addEventListener("submit", (event) => {
  event.preventDefault();
  launch("run", configSelect.value);
});
get("analyze").addEventListener("click", () => launch("analyze", runSelect.value));
get("results-button").addEventListener("click", () => {
  showView("results");
  requestAnimationFrame(() => observer && fitReport());
});
get("console-button").addEventListener("click", () => showView("console"));
configSelect.addEventListener("change", showConfig);
runSelect.addEventListener("change", () => showRun());
function fitReport() {
  const main = report.contentDocument?.querySelector("main");
  if (main && !report.hidden && !get("results").hidden) report.style.height = `${main.scrollHeight + 4}px`;
}
report.addEventListener("load", () => {
  observer?.disconnect();
  if (!report.contentDocument?.body) return;
  report.contentDocument.body.classList.add("embedded");
  const main = report.contentDocument.querySelector("main");
  if (!main) return;
  observer = new ResizeObserver(fitReport);
  observer.observe(main);
  fitReport();
});
loadCatalog().catch((error) => notice(error.message));
poll();
