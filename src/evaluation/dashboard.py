"""A standalone HTML view of one Phase 7 batch."""
import json
import math
from collections import Counter
from html import escape


def percent(value):
    return "—" if value is None else f"{value:.1%}"


def render_project_dashboard(runs, skipped):
    sections = []
    for group in [runs] if runs else []:
        cards = []
        for run in group:
            rows = []
            for policy, row in run["summary"].items():
                calls = row["verifier_calls_per_action"]
                values = (
                    f'{row["completed"]}/{row["planned"]}',
                    percent(row["success_rate"] if row["completed"] else None),
                    row["verify_triggered"], row["verifier_calls"], percent(row["selection_rate"]),
                    "—" if calls is None else f"{calls:.2f}",
                    sum(row["verifier_usage"].values()), f'{row["verifier_latency_ms"] / 1000:.2f} s',
                    row["recovery_attempts"],
                )
                cells = "".join(f"<td>{value}</td>" for value in values)
                rows.append(f'<tr><th scope="row">{escape(policy)}</th>{cells}</tr>')
            mode = ("Offline scripted run" if run["provider"] == "scripted"
                    else f'{run["provider"]} · {run["model"]}')
            cards.append(f"""<article>
<div class="run-head"><div><h3>{escape(mode)}</h3>
<p>Run {escape(run["id"])} · fault rate {run["fault_rate"]:.0%}</p></div>
<a href="{escape(run["href"])}">Open run details</a></div>
<div class="scroll" tabindex="0" role="region" aria-label="Policy metrics for run {escape(run["id"])}">
<table><thead><tr><th>Policy</th><th>Completed</th><th>Oracle success</th>
<th>Selected actions</th><th>Verifier calls</th><th>Selection rate</th><th>Calls / action</th>
<th>Verifier tokens</th><th>Verifier time</th><th>Retries</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></article>""")
        sections.append(f"<section><h2>Saved runs</h2>{''.join(cards)}</section>")
    content = "".join(sections) or "<p>No experiment reports are available yet.</p>"
    warnings = ""
    if skipped:
        items = "".join(f"<li>{escape(item)}</li>" for item in skipped)
        warnings = f"<section><h2>Unreadable run logs</h2><ul>{items}</ul></section>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CostAware project dashboard</title>
<style>
:root {{ --paper:#f5f2ec;--surface:#fffdf8;--ink:#252b26;--muted:#575e55;--line:#dedbd0;--accent:#28594d }}
* {{ box-sizing:border-box }}
body {{ margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,sans-serif }}
main {{ max-width:1240px;margin:auto;padding:48px clamp(12px,4vw,48px) }}
header {{ border-top:4px solid var(--accent);padding-top:18px;margin-bottom:28px }}
h1 {{ font:600 clamp(32px,5vw,54px)/1.08 Georgia,serif;margin:0 0 12px;letter-spacing:-.035em }}
h2 {{ font:600 28px/1.2 Georgia,serif;margin:24px 0 10px }}
h3 {{ color:var(--accent);font-size:1rem;margin:0 0 4px }} p {{ margin:0;color:var(--muted);overflow-wrap:anywhere }}
article {{ background:var(--surface);border:1px solid var(--line);padding:clamp(12px,3vw,28px);margin-bottom:12px }}
.run-head {{ display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:16px }}
a {{ color:var(--accent);font-weight:650;text-underline-offset:3px }}
.scroll {{ overflow-x:auto }} table {{ width:100%;border-collapse:collapse;font-size:.85rem;font-variant-numeric:tabular-nums }}
th,td {{ text-align:left;padding:9px 8px;border-bottom:1px solid var(--line) }}
thead th {{ vertical-align:bottom;background:#eeece3;color:var(--muted) }} tbody td {{ white-space:nowrap }}
tbody tr:last-child > * {{ border-bottom:0 }}
a:focus-visible,.scroll:focus-visible {{ outline:2px solid var(--accent);outline-offset:3px }}
</style></head><body><main>
<header><h1>CostAware project dashboard</h1>
<p>Saved experiment results. Open a run for its reliability chart, matched comparisons, and episode traces.</p></header>
{content}{warnings}</main></body></html>"""


def reliability_plot(summary):
    coordinates = {}
    for policy, row in summary.items():
        rate = row["verifier_calls_per_action"]
        success = row["success_rate"]
        if rate is not None and success is not None and row.get("completed") != 0:
            coordinates.setdefault((rate, success), []).append(policy)
    if not coordinates:
        return '<p class="empty">No agent actions with a completed policy outcome are available to plot.</p>'
    maximum = max(1, math.ceil(max(rate for rate, _ in coordinates) * 2) / 2)
    ticks = range(0, 101, 25)
    guides = "".join(
        f'<span class="guide horizontal" style="bottom:{tick}%"><span>{tick}%</span></span>'
        for tick in ticks
    ) + "".join(
        f'<span class="guide vertical" style="left:{tick}%"><span>{maximum * tick / 100:.2f}</span></span>'
        for tick in ticks
    )
    points = []
    keys = []
    for (rate, success), policies in coordinates.items():
        label = escape(" / ".join(policies))
        description = f"{label} · {percent(success)} oracle success · {rate:.2f} calls per action"
        color = policies[0] if len(policies) == 1 else "shared"
        points.append(f'<span class="point policy-{color}" style="left:{rate / maximum:.6%};'
                      f'bottom:{success:.6%}" title="{description}">{label}</span>')
        keys.append(f'<li><span class="swatch policy-{color}">{label}</span>'
                    f'<span>{percent(success)} <small>success</small></span>'
                    f'<span>{rate:.2f} <small>calls / action</small></span></li>')
    return f"""<figure aria-label="Oracle success rate versus verifier calls per agent action">
<div class="y-label">Oracle success rate</div>
<div class="plot-frame" aria-hidden="true"><div class="plot">{guides}{''.join(points)}</div></div>
<figcaption>Verifier calls per agent action</figcaption>
<ul class="plot-key">{''.join(keys)}</ul></figure>"""


def render_dashboard(header, episodes, summary, pairs):
    config = header["config"]
    failures = Counter(episode["result"].get("error") or "Unknown error"
                       for episode in episodes if episode["status"] == "error")
    note = ""
    if failures:
        items = "".join(f"<li>{escape(error)} · {count} episode(s)</li>"
                        for error, count in failures.most_common())
        failed_episodes = [episode for episode in episodes if episode["status"] == "error"]
        recorded_calls = sum(len(episode["trajectory"]) for episode in failed_episodes)
        agent_usage = sum(sum(episode["result"].get("agent_usage", {}).values())
                          for episode in failed_episodes)
        partial = (f"<p>Before the error, the run recorded <strong>{recorded_calls} tool "
                   f"calls</strong> and <strong>{agent_usage:,} agent tokens</strong>. "
                   '<a href="#episode-traces">View the recorded actions</a>.</p>') if recorded_calls else ""
        missing_outcome = ("<p>No episode finished, so this run has no oracle success rate.</p>"
                           if not any(row["completed"] for row in summary.values()) else "")
        note = f'<section><h2>Run errors</h2><ul>{items}</ul>{partial}{missing_outcome}</section>'
    rows = []
    diagnostics = []
    for policy, row in summary.items():
        cells = (
            policy, f'{row["completed"]}/{row["planned"]}',
            percent(row["success_rate"] if row["completed"] else None),
            row["verify_triggered"], row["verifier_calls"], percent(row["selection_rate"]),
            "—" if row["verifier_calls_per_action"] is None else f'{row["verifier_calls_per_action"]:.2f}',
            sum(row["verifier_usage"].values()), f'{row["verifier_latency_ms"] / 1000:.2f} s',
            row["recovery_attempts"], row["verifier_errors"],
            percent(row["fault_recovery_rate"]), percent(row["error_propagation_rate"]),
        )
        rows.append(f'<tr><th scope="row"><span class="swatch policy-{policy}">{policy}</span></th>'
                    + "".join(f"<td>{value}</td>" for value in cells[1:]) + "</tr>")
        diagnostic = row["diagnostics"]
        counts = diagnostic["verdict_counts"]
        reasons = ", ".join(f"{reason}: {count}" for reason, count in sorted(diagnostic["triggers"].items()))
        values = (
            percent(diagnostic["trigger_precision"]), percent(diagnostic["trigger_recall"]),
            f'{diagnostic["selected_faulted_actions"]}/{diagnostic["faulted_actions"]}',
            percent(diagnostic["verifier_false_positive_rate"]),
            percent(diagnostic["verifier_false_negative_rate"]),
            sum(counts.values()), percent(row["verifier_error_rate"]), reasons or "—",
        )
        diagnostics.append(f'<tr><th scope="row">{policy}</th>'
                           + "".join(f"<td>{escape(str(value))}</td>" for value in values) + "</tr>")
    details = []
    for episode in episodes:
        verdict = episode["result"].get("oracle_pass")
        outcome = episode["status"]
        if episode["result"].get("done_reason") == "truncated":
            outcome = "TRUNCATED"
        elif outcome == "completed":
            outcome = "PASS" if verdict else "FAIL"
        label = escape(f'{episode["task_id"]} · Policy {episode["policy"]} · '
                       f'seed {episode["seed"]} · {outcome}')
        payload = escape(json.dumps(episode, indent=2, ensure_ascii=False))
        details.append(f"<details><summary>{label}</summary><pre>{payload}</pre></details>")
    badge = ("Offline scripted run" if config["provider"] == "scripted" else
             f'{escape(config["provider"])} · {escape(config["model"])}')
    headings = ("Policy", "Completed", "Oracle success", "Selected actions", "Verifier calls",
                "Selection rate", "Calls / action", "Verifier tokens", "Verifier time", "Retries",
                "Verifier errors", "Faulted pass rate", "Faulted fail rate")
    comparison = []
    for policy, pair in pairs.items():
        interval = pair["success_delta_ci95"]
        bounds = "—" if interval is None else f"{percent(interval[0])} to {percent(interval[1])}"
        comparison.append(f'<li>{policy} vs B · {pair["pairs"]} pairs across {pair["tasks"]} tasks · '
                          f'outcome difference {pair["success_delta"] * 100:+.1f} pp '
                          f'(95% interval {bounds}) · {pair["calls_delta"]:+.2f} calls per episode</li>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CostAware experiment dashboard</title>
<style>
:root {{ --paper:#f5f2ec;--surface:#fffdf8;--ink:#252b26;--muted:#575e55;--line:#dedbd0;
--accent:#28594d;--grid:#e6e2d8 }}
* {{ box-sizing:border-box }}
body {{ margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,sans-serif }}
main {{ max-width:1240px;margin:auto;padding:48px clamp(12px,4vw,48px) }}
header {{ border-top:4px solid var(--accent);padding-top:16px;margin-bottom:26px }}
h1 {{ font:600 clamp(32px,5vw,54px)/1.08 Georgia,serif;margin:8px 0 12px;letter-spacing:-.035em }}
h2 {{ font:600 24px/1.2 Georgia,serif;margin:0 0 10px }} p {{ margin:0 0 14px;color:var(--muted) }}
header p {{ overflow-wrap:anywhere }} .run-mode {{ color:var(--accent);font-size:.85rem;font-weight:650 }}
.embedded {{ background:var(--surface) }} .embedded main {{ padding:0 }}
.embedded header {{ border-top:0;padding-top:0;margin-bottom:10px }}
.embedded h1 {{ display:none }}
section {{ background:var(--surface);border:1px solid var(--line);padding:clamp(12px,3vw,28px);margin-top:16px }}
.scroll {{ overflow-x:auto }} table {{ width:100%;border-collapse:collapse;font-size:.85rem;font-variant-numeric:tabular-nums }}
td,th {{ padding:10px 8px;text-align:left;border-bottom:1px solid var(--line) }}
thead th {{ vertical-align:bottom;background:#eeece3;color:var(--muted) }} tbody td {{ white-space:nowrap }}
tbody tr:last-child > * {{ border-bottom:0 }}
.policy-A {{ --policy:#4d5b65 }} .policy-B {{ --policy:#8a4939 }}
.policy-C {{ --policy:#765a24 }} .policy-D {{ --policy:#28594d }} .policy-shared {{ --policy:#434a42 }}
.swatch,.point {{ background:var(--policy);color:white;font-weight:700;font-size:.74rem;line-height:1.3;
display:inline-block;text-align:center;min-width:23px;padding:3px 6px;border-radius:3px;white-space:nowrap }}
figure {{ margin:0 }} .y-label,figcaption {{ color:var(--muted);font-size:.82rem;font-weight:600 }}
.plot-frame {{ overflow-x:auto }} .plot {{ position:relative;height:215px;width:calc(100% - 90px);
margin:20px 34px 29px 56px;min-width:260px;border-left:1px solid var(--muted);
border-bottom:1px solid var(--muted) }}
.guide {{ position:absolute;color:var(--muted);font-size:.73rem;font-variant-numeric:tabular-nums }}
.guide.horizontal {{ width:100%;border-top:1px solid var(--grid) }}
.guide.horizontal:first-child {{ border-color:transparent }}
.guide.horizontal span {{ position:absolute;right:calc(100% + 17px);transform:translateY(-50%) }}
.guide.vertical {{ height:100%;bottom:0;border-left:1px solid var(--grid) }}
.guide.vertical span {{ position:absolute;top:calc(100% + 7px);transform:translateX(-50%) }}
.point {{ position:absolute;transform:translate(-50%,50%);z-index:1;outline:2px solid var(--surface) }}
figcaption {{ text-align:center }} .plot-key {{ display:flex;flex-wrap:wrap;gap:8px 20px;list-style:none;
padding:14px 0 0;margin:16px 0 0;border-top:1px solid var(--line);font-size:.83rem }}
.plot-key li {{ display:flex;align-items:center;gap:8px }} .plot-key small {{ color:var(--muted) }}
details {{ border-top:1px solid var(--line);padding:10px 0 }} summary {{ cursor:pointer }}
pre {{ white-space:pre-wrap;overflow-wrap:anywhere;font-size:.83rem;background:var(--paper);padding:12px }}
a:focus-visible,summary:focus-visible,.scroll:focus-visible {{ outline:2px solid var(--accent);outline-offset:3px }}
</style></head><body><main>
<header><span class="run-mode">{badge}</span><h1>CostAware experiment dashboard</h1>
<p>Run {escape(header["run_id"])} · fault rate {config["fault_rate"]:.0%}</p></header>
{note}
<section><h2>Reliability versus verification workload</h2>
{reliability_plot(summary)}</section>
<section><h2>Policy comparison</h2>
<p>Success uses all planned episodes when a policy has completed at least one episode.
Verifier calls include retry rechecks.</p>
<div class="scroll" tabindex="0" role="region" aria-label="Policy comparison table"><table><thead><tr>{''.join(f'<th scope="col">{name}</th>' for name in headings)}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<section><h2>Verification diagnostics</h2>
<p>Selection uses original agent actions. Verdict rates use valid checks, including retry checks.
Injected faults are the reference labels. An uncorrupted response can still warrant suspicion.</p>
<div class="scroll" tabindex="0" role="region" aria-label="Verification diagnostics table">
<table><thead><tr><th>Policy</th><th>Trigger precision</th><th>Trigger recall</th><th>Faulted actions selected</th>
<th>False positive rate</th><th>False negative rate</th><th>Valid verdicts</th><th>Verifier error rate</th>
<th>Trigger reasons</th></tr></thead><tbody>{''.join(diagnostics)}</tbody></table></div></section>
<section><h2>Matched comparisons with Policy B</h2>
<p>Completed pairs only. Outcome intervals resample whole tasks. Small batches are intended for validation.</p>
<ul>{''.join(comparison) or '<li>No completed pairs with Policy B.</li>'}</ul></section>
<section id="episode-traces"><h2>Episode traces</h2>{''.join(details)}</section>
<section><h2>Run configuration</h2><pre>{escape(json.dumps(config, indent=2))}</pre></section>
</main></body></html>"""
