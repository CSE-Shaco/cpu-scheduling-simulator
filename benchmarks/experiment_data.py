"""Validated, deterministic scheduling outcomes; all time is simulated time."""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE_WORKLOADS = ("convoy", "staggered", "idle-gaps", "equal-bursts", "bursty", "mixed-bounded")
PREFIX_STUDIES = {
    f"{family}-h{horizon:03d}": {"family": family, "horizon": horizon}
    for family in ("ready-short-stream", "late-short-stream") for horizon in (16, 32, 64, 128)
}
WORKLOADS = BASE_WORKLOADS + tuple(PREFIX_STUDIES)
CONFIGS = (("fcfs", 2), ("sjf", 2), ("srtf", 2), ("rr", 1), ("rr", 2), ("rr", 4), ("rr", 8))
METRIC_HEADER = "id,arrival,burst,start,completion,waiting,turnaround,response"
SEGMENT = re.compile(r"\[(\d+),(\d+)\) ([A-Za-z0-9_-]+)\Z")
SUMMARY = re.compile(r"makespan=(\d+) busy=(\d+) idle=(\d+) switching=(\d+) context_switches=(\d+) average_waiting=([0-9]+\.[0-9]{3}) average_turnaround=([0-9]+\.[0-9]{3})\Z")


def case_specs():
    return ([(w, p, q, c) for w in BASE_WORKLOADS for p, q in CONFIGS for c in (0, 1)]
            + [(w, p, 2, 0) for w in PREFIX_STUDIES for p in ("fcfs", "sjf", "srtf", "rr")])


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_tasks(path):
    return parse_tasks(Path(path).read_bytes().decode("utf-8"))


def parse_tasks(text):
    reader = csv.DictReader(io.StringIO(text, newline=""))
    require(reader.fieldnames == ["id", "arrival", "burst"], "unexpected workload header")
    tasks = []
    for row in reader:
        require(set(row) == {"id", "arrival", "burst"}, "unexpected workload fields")
        name, arrival, burst = row["id"], row["arrival"], row["burst"]
        require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,63}", name)
                and name not in ("IDLE", "SWITCH"), "invalid task ID")
        require(isinstance(arrival, str) and isinstance(burst, str) and arrival.isdigit() and burst.isdigit(), "invalid workload number")
        arrival, burst = int(arrival), int(burst)
        require(burst > 0 and arrival <= 10000 and burst <= 10000, "workload outside experiment bounds")
        tasks.append((name, arrival, burst))
    require(tasks and len(tasks) <= 256 and len({t[0] for t in tasks}) == len(tasks), "empty/duplicate/oversized workload")
    require(max(t[1] for t in tasks) + sum(t[2] for t in tasks) <= 100000, "tick-oracle workload too large")
    return tasks


def tick_oracle(tasks, policy, quantum):
    """Use the existing independent integer-tick oracle, not the C event engine."""
    spec = importlib.util.spec_from_file_location("scheduler_tick_oracle", ROOT / "tests/differential.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.oracle(tasks, policy, quantum)


def parse_output(text, tasks, context_cost):
    lines = text.splitlines()
    require(lines and lines[0] == "Gantt (half-open intervals)", "missing Gantt header")
    require(lines.count(METRIC_HEADER) == 1, "missing/duplicate metric header")
    boundary = lines.index(METRIC_HEADER)
    require(len(lines) == boundary + len(tasks) + 2, "unexpected output row count")
    by_id = {t[0]: t for t in tasks}
    served = {name: 0 for name in by_id}
    first, last, segments = {}, {}, []
    totals = {"busy": 0, "idle": 0, "switching": 0}
    end = 0
    previous = None
    switches = 0
    for line in lines[1:boundary]:
        match = SEGMENT.fullmatch(line)
        require(match is not None, "invalid Gantt interval")
        start, stop, name = int(match[1]), int(match[2]), match[3]
        require(start == end and stop > start, "Gantt gap, overlap or empty interval")
        duration = stop - start
        if name == "IDLE":
            require(not any(arrival < stop and served[task] < burst for task, arrival, burst in tasks), "idle CPU with pending task")
            totals["idle"] += duration
            previous = None
        elif name == "SWITCH":
            require(previous is not None and context_cost > 0 and duration == context_cost, "invalid context-switch interval")
            totals["switching"] += duration
        else:
            require(name in by_id, "unknown task in Gantt")
            require(start >= by_id[name][1], "task executes before arrival")
            if previous is not None and previous != name:
                switches += 1
            served[name] += duration
            require(served[name] <= by_id[name][2], "task consumes excess service")
            first.setdefault(name, start)
            last[name] = stop
            previous = name
            totals["busy"] += duration
        segments.append({"start": start, "end": stop, "task": name})
        end = stop
    require(segments and segments[-1]["task"] not in ("IDLE", "SWITCH"), "trailing non-service segment")
    require(all(served[name] == burst for name, _, burst in tasks), "missing task service")
    rows = list(csv.reader(io.StringIO("\n".join(lines[boundary + 1:-1]))))
    metrics = []
    for row, (name, arrival, burst) in zip(rows, tasks):
        require(len(row) == 8 and row[0] == name, "metric task/order mismatch")
        require(all(re.fullmatch(r"\d+", value) for value in row[1:]), "invalid metric integer")
        a, b, start, completion, waiting, turnaround, response = map(int, row[1:])
        require((a, b) == (arrival, burst), "metric input mismatch")
        require(start == first[name] and completion == last[name], "metric/timeline mismatch")
        require(turnaround == completion - arrival and waiting == turnaround - burst
                and response == start - arrival and waiting >= 0 and 0 <= response <= waiting, "metric accounting mismatch")
        metrics.append(dict(zip(METRIC_HEADER.split(","), [name, a, b, start, completion, waiting, turnaround, response])))
    summary = SUMMARY.fullmatch(lines[-1])
    require(summary is not None, "invalid summary")
    makespan, busy, idle, switching, context_switches = map(int, summary.groups()[:5])
    require(makespan == end == sum(totals.values()) and busy == totals["busy"]
            and idle == totals["idle"] and switching == totals["switching"], "global timeline accounting mismatch")
    require(context_switches == switches and switching == switches * context_cost, "switch-count accounting mismatch")
    averages = {field: sum(m[field] for m in metrics) / len(metrics)
                for field in ("waiting", "turnaround", "response")}
    require(abs(float(summary[6]) - averages["waiting"]) <= 0.000501
            and abs(float(summary[7]) - averages["turnaround"]) <= 0.000501, "rounded console average mismatch")
    return {"tasks": metrics, "timeline": segments,
            "metrics": {"task_count": len(tasks), "makespan": makespan, **totals,
                        "context_switches": context_switches,
                        **{"average_" + key: value for key, value in averages.items()},
                        **{"maximum_" + key: max(m[key] for m in metrics)
                           for key in ("waiting", "turnaround", "response")},
                        "productive_utilization_percent": 100 * busy / makespan,
                        "switching_percent": 100 * switching / makespan}}


def prefix_metrics(parsed, horizon):
    """Observe a finite [0,H) prefix; never count time after LONG completes."""
    long_job = next(m for m in parsed["tasks"] if m["id"] == "LONG")
    limit = min(horizon, long_job["completion"])
    cursor, service, maximum_gap = long_job["arrival"], 0, 0
    for segment in parsed["timeline"]:
        if segment["task"] != "LONG":
            continue
        start, end = max(segment["start"], long_job["arrival"]), min(segment["end"], limit)
        if end <= start:
            continue
        maximum_gap = max(maximum_gap, start - cursor)
        service += end - start
        cursor = end
    maximum_gap = max(maximum_gap, limit - cursor)
    return {"observation_horizon": horizon, "long_first_start": long_job["start"],
            "long_completion": long_job["completion"], "long_waiting": long_job["waiting"],
            "long_service_before_horizon": service,
            "long_max_ready_gap_before_horizon": maximum_gap,
            "long_done_by_horizon": long_job["completion"] <= horizon}


def label(policy, quantum):
    return "RR q=" + str(quantum) if policy == "rr" else policy.upper()


def case_name(workload, policy, quantum, cost):
    return f"{workload}-{policy}-q{quantum}-c{cost}"


def load_run(directory):
    directory = Path(directory).resolve()
    metadata = json.loads((directory / "metadata.json").read_text())
    require(type(metadata.get("schema_version")) is int and metadata["schema_version"] == 1
            and metadata.get("status") == "complete", "experiment is incomplete")
    require(metadata.get("operation") == "deterministic_scheduling_policy_sweep", "unexpected experiment operation")
    require(metadata.get("completed_cases") == metadata.get("expected_case_count") == 116,
            "experiment case count mismatch")
    require(set(metadata.get("workloads", {})) == set(WORKLOADS), "workload matrix mismatch")
    for workload in metadata["workloads"].values():
        require(isinstance(workload.get("csv_text"), str)
                and hashlib.sha256(workload["csv_text"].encode("utf-8")).hexdigest() == workload.get("sha256"),
                "workload snapshot digest mismatch")
        require([list(t) for t in parse_tasks(workload["csv_text"])] == workload.get("tasks"),
                "workload snapshot/tasks mismatch")
    records = json.loads((directory / "records.json").read_text())
    require(len(records) == 116, "expected all 116 experiment configurations")
    output_files = ("records.json", "analysis/summary.json", "analysis/summary.csv",
                    "analysis/policy-comparison.svg", "analysis/round-robin-tradeoff.svg",
                    "analysis/finite-postponement.svg")
    require(set(metadata.get("result_sha256", {})) == set(output_files), "result digest set mismatch")
    require(all(metadata["result_sha256"][name] == sha256(directory / name) for name in output_files), "result digest mismatch")
    commands = metadata.get("commands")
    require(isinstance(commands, list) and len(commands) == 116, "missing experiment commands")
    expected = set(case_specs())
    actual = set()
    for index, record in enumerate(records):
        require(type(record.get("quantum")) is int and type(record.get("context_cost")) is int,
                "invalid numeric experiment options")
        key = (record["workload"], record["policy"], record["quantum"], record["context_cost"])
        require(key in expected and key not in actual, "duplicate/unexpected experiment configuration")
        actual.add(key)
        name = case_name(*key)
        require(commands[index].get("case") == name and commands[index].get("returncode") == 0,
                "command order/status mismatch")
        tasks = [tuple(t) for t in metadata["workloads"][key[0]]["tasks"]]
        stdout = directory / "raw" / (name + ".stdout.txt")
        stderr = directory / "raw" / (name + ".stderr.txt")
        require(sha256(stdout) == record["stdout_sha256"] and sha256(stderr) == record["stderr_sha256"], "raw output digest mismatch")
        require(not stderr.read_text().strip() and record["returncode"] == 0, "failed simulator command")
        parsed = parse_output(stdout.read_text(), tasks, key[3])
        require(parsed == {field: record[field] for field in ("tasks", "timeline", "metrics")}, "record disagrees with raw simulator output")
        if key[0] in PREFIX_STUDIES:
            require(record.get("cohort") == "finite-postponement"
                    and record.get("prefix_metrics") == prefix_metrics(parsed, PREFIX_STUDIES[key[0]]["horizon"]),
                    "finite-prefix metrics disagree with timeline")
        else:
            require(record.get("cohort") == "policy-comparison" and record.get("prefix_metrics") is None,
                    "unexpected experiment cohort")
        if key[3] == 0:
            expected_times = tick_oracle(tasks, key[1], key[2])
            require([(r["start"], r["completion"]) for r in parsed["tasks"]] == expected_times, "zero-cost tick-oracle mismatch")
    require(actual == expected, "missing experiment configuration")
    require(summaries(records) == json.loads((directory / "analysis/summary.json").read_text()),
            "derived summary disagrees with records")
    return metadata, records


def summaries(records):
    empty_prefix = {key: None for key in ("observation_horizon", "long_first_start", "long_completion", "long_waiting",
                                        "long_service_before_horizon", "long_max_ready_gap_before_horizon", "long_done_by_horizon")}
    return [{"cohort": r["cohort"], "workload": r["workload"], "policy": r["policy"], "quantum": r["quantum"],
             "context_cost": r["context_cost"], **r["metrics"], **(r["prefix_metrics"] or empty_prefix)} for r in records]


def write_analysis(records, destination):
    """Derived outcomes, not wall-clock samples or universal policy rankings."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    rows = summaries(records)
    (destination / "summary.json").write_text(json.dumps(rows, indent=2, allow_nan=False) + "\n")
    with (destination / "summary.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _draw_policy(rows, destination / "policy-comparison.svg")
    _draw_quantum(rows, destination / "round-robin-tradeoff.svg")
    _draw_prefix(rows, destination / "finite-postponement.svg")


def _draw_policy(rows, path):
    width, height = 1160, 930
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>', '<g font-family="sans-serif" fill="#162b3a">',
           '<text x="24" y="30" font-size="21">Scheduling policy outcomes: zero context-switch cost</text>',
           '<text x="24" y="55" font-size="13">Blue: mean waiting. Orange: mean response. Abstract simulation units; lower is better.</text>']
    for index, workload in enumerate(BASE_WORKLOADS):
        x, y = 30 + (index % 2) * 570, 92 + (index // 2) * 275
        cases = [next(r for r in rows if (r["workload"], r["policy"], r["quantum"], r["context_cost"]) == (workload, p, q, 0)) for p, q in CONFIGS]
        maximum = max(r["average_waiting"] for r in cases) * 1.12 or 1
        svg.append(f'<text x="{x}" y="{y}" font-size="16" font-weight="700">{workload}</text>')
        for tick in range(5):
            value = maximum * tick / 4
            py = y + 190 - 155 * tick / 4
            svg.extend((f'<path d="M{x+35},{py:.2f} H{x+530}" stroke="#e1e7ec"/>',
                        f'<text x="{x}" y="{py+4:.2f}" font-size="10">{value:.1f}</text>'))
        for k, row in enumerate(cases):
            px = x + 48 + k * 69
            for offset, field, color in ((0, "average_waiting", "#286ba6"), (22, "average_response", "#ce7429")):
                h = row[field] / maximum * 155
                svg.append(f'<rect x="{px+offset}" y="{y+190-h:.3f}" width="20" height="{h:.3f}" fill="{color}"/>')
            svg.append(f'<text x="{px-3}" y="{y+212}" font-size="10">{label(row["policy"], row["quantum"])}</text>')
    svg.append('<text x="24" y="910" font-size="12">Same workload for every policy. Finite CPU-only bursts; no real-kernel or host-runtime performance claim.</text></g></svg>')
    path.write_text("\n".join(svg) + "\n")


def _draw_prefix(rows, path):
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="690" viewBox="0 0 1160 690">',
           '<rect width="100%" height="100%" fill="white"/>', '<g font-family="sans-serif" fill="#162b3a">',
           '<text x="24" y="30" font-size="21">Finite short-job streams: long-job progress and postponement</text>',
           '<text x="24" y="55" font-size="13">FCFS: blue. SJF: orange. SRTF: green. RR q=2: purple. Switch cost = 0.</text>',
           '<text x="24" y="76" font-size="12">Full simulations finish. These plots observe [0,H); finite prefixes do not prove infinite starvation.</text>']
    colors = {"fcfs": "#286ba6", "sjf": "#ce7429", "srtf": "#26836b", "rr": "#8050a2"}
    for fi, family in enumerate(("ready-short-stream", "late-short-stream")):
        for mi, (field, title) in enumerate((("long_service_before_horizon", "LONG service before H"),
                                             ("long_max_ready_gap_before_horizon", "Longest ready/no-service gap before H"))):
            x, y = 30 + fi * 570, 120 + mi * 255
            maximum = 64 if mi == 0 else 128
            svg.append(f'<text x="{x}" y="{y}" font-size="15" font-weight="700">{family}: {title}</text>')
            for tick in range(5):
                py = y + 180 - tick * 140 / 4
                svg.extend((f'<path d="M{x+45},{py:.2f} H{x+510}" stroke="#e1e7ec"/>',
                            f'<text x="{x}" y="{py+4:.2f}" font-size="10">{maximum*tick/4:.0f}</text>'))
            for policy, color in colors.items():
                points = []
                for hi, horizon in enumerate((16, 32, 64, 128)):
                    name = f"{family}-h{horizon:03d}"
                    row = next(r for r in rows if r["workload"] == name and r["policy"] == policy)
                    points.append((x + 70 + hi * 135, y + 180 - row[field] / maximum * 140))
                svg.append('<polyline fill="none" stroke="' + color + '" stroke-width="2" points="' + ' '.join(f'{px:.3f},{py:.3f}' for px, py in points) + '"/>')
                svg.extend(f'<circle cx="{px:.3f}" cy="{py:.3f}" r="4" fill="{color}"/>' for px, py in points)
            for hi, horizon in enumerate((16, 32, 64, 128)):
                svg.append(f'<text x="{x+60+hi*135}" y="{y+202}" font-size="11">H={horizon}</text>')
    svg.append('<text x="24" y="650" font-size="12">Horizon positions are categorical. Equal curves overlap; exact values and first-start/completion are in summary.csv.</text></g></svg>')
    path.write_text("\n".join(svg) + "\n")


def _draw_quantum(rows, path):
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="670" viewBox="0 0 1160 670">',
           '<rect width="100%" height="100%" fill="white"/>', '<g font-family="sans-serif" fill="#162b3a">',
           '<text x="24" y="30" font-size="21">Round Robin quantum and context-switch tradeoffs</text>',
           '<text x="24" y="55" font-size="13">Blue: switch cost 0. Orange: switch cost 1. Points are deterministic simulation outcomes.</text>']
    for wi, workload in enumerate(("convoy", "mixed-bounded")):
        for mi, (field, title, unit) in enumerate((("average_response", "Mean response", "time units; lower is better"), ("productive_utilization_percent", "Productive utilization", "busy / makespan (%); higher is better"))):
            x, y = 30 + mi * 570, 100 + wi * 265
            cases = {(q, c): next(r for r in rows if (r["workload"], r["policy"], r["quantum"], r["context_cost"]) == (workload, "rr", q, c)) for q in (1, 2, 4, 8) for c in (0, 1)}
            maximum = 100 if mi else max(r[field] for r in cases.values()) * 1.15 or 1
            svg.extend((f'<text x="{x}" y="{y}" font-size="16" font-weight="700">{workload}: {title}</text>',
                        f'<text x="{x}" y="{y+18}" font-size="11">{unit}</text>'))
            for tick in range(5):
                py = y + 190 - tick * 145 / 4
                svg.extend((f'<path d="M{x+45},{py:.2f} H{x+510}" stroke="#e1e7ec"/>',
                            f'<text x="{x}" y="{py+4:.2f}" font-size="10">{maximum*tick/4:.1f}</text>'))
            for cost, color in ((0, "#286ba6"), (1, "#ce7429")):
                points = [(x + 70 + qi * 135, y + 190 - cases[(q, cost)][field] / maximum * 145) for qi, q in enumerate((1, 2, 4, 8))]
                svg.append('<polyline fill="none" stroke="' + color + '" stroke-width="2" points="' + ' '.join(f'{px:.3f},{py:.3f}' for px, py in points) + '"/>')
                svg.extend(f'<circle cx="{px:.3f}" cy="{py:.3f}" r="4" fill="{color}"/>' for px, py in points)
            for qi, q in enumerate((1, 2, 4, 8)):
                svg.append(f'<text x="{x+65+qi*135}" y="{y+210}" font-size="11">q={q}</text>')
    svg.append('<text x="24" y="650" font-size="12">Quantum positions are categorical. Other workload outcomes remain in summary.csv; no universal winning policy is inferred.</text></g></svg>')
    path.write_text("\n".join(svg) + "\n")
