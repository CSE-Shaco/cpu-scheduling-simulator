#!/usr/bin/env python3
"""Run 116 deterministic scheduling case studies; never report host speedups."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

from experiment_data import (CONFIGS, PREFIX_STUDIES, ROOT, WORKLOADS, case_name, case_specs, load_tasks,
                             parse_output, prefix_metrics, require, sha256, tick_oracle, write_analysis)


def now():
    return datetime.now(timezone.utc).isoformat()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--build-command", required=True,
                        help="exact compiler invocation used; recorded as operator-supplied provenance")
    parser.add_argument("--compiler", default="cc", help="compiler executable for the version probe")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)
    binary, out = args.binary.resolve(), args.out.resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        parser.error("binary must be an existing executable")
    if args.out.exists() or args.out.is_symlink():
        parser.error("output exists; choose a new directory")
    if not args.timeout > 0 or not args.timeout < float("inf"):
        parser.error("timeout must be positive and finite")
    if not args.build_command.strip():
        parser.error("build command must not be empty")
    workload_paths = {name: ROOT / "workloads" / (name + ".csv") for name in WORKLOADS}
    try:
        workloads = {name: load_tasks(path) for name, path in workload_paths.items()}
        version = subprocess.run([args.compiler, "--version"], text=True, capture_output=True,
                                 timeout=args.timeout, check=True)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    sources = [ROOT / "include/scheduler.h", ROOT / "src/simulator.c", ROOT / "src/main.c",
               ROOT / "tests/differential.py", *sorted((ROOT / "benchmarks").glob("*.py"))]
    source_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in sources}
    binary_hash = sha256(binary)
    metadata = {
        "schema_version": 1, "operation": "deterministic_scheduling_policy_sweep",
        "status": "running", "started_utc": now(), "host": platform.platform(),
        "python": platform.python_version(), "time_unit": "abstract simulation units",
        "build_command": args.build_command, "build_command_attestation": "operator supplied; not inferred from binary",
        "compiler_probe_command": [args.compiler, "--version"], "compiler_version": version.stdout.strip(),
        "binary_sha256": binary_hash, "source_sha256": source_hashes,
        "workloads": {name: {"path": str(path.relative_to(ROOT)), "sha256": sha256(path),
                              "csv_text": path.read_bytes().decode("utf-8"), "tasks": workloads[name]}
                      for name, path in workload_paths.items()},
        "policies": [{"policy": p, "quantum": q} for p, q in CONFIGS], "context_costs": [0, 1],
        "expected_case_count": 116, "cohorts": {"policy-comparison": 84, "finite-postponement": 32},
        "finite_prefix_studies": PREFIX_STUDIES, "commands": [], "completed_cases": 0,
        "validation_scope": "timeline/service/metric accounting for all cases; independent tick oracle for 74 zero-cost cases",
        "limits": "Finite CPU-only simulated workloads; not host timings, real-kernel performance, or universal policy rankings."
    }
    records = []
    out.mkdir(parents=True, exist_ok=False)
    (out / "raw").mkdir()

    def save():
        (out / "metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")
        (out / "records.json").write_text(json.dumps(records, indent=2, allow_nan=False) + "\n")

    save()
    try:
        for workload, policy, quantum, cost in case_specs():
            tasks = workloads[workload]
            name = case_name(workload, policy, quantum, cost)
            command = [str(binary), str(workload_paths[workload].relative_to(ROOT)),
                       "--policy", policy, "--quantum", str(quantum), "--context-switch", str(cost)]
            entry = {"case": name, "command": command, "cwd": "repository root", "started_utc": now()}
            metadata["commands"].append(entry)
            save()
            try:
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                        timeout=args.timeout, check=True)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                for stream in ("stdout", "stderr"):
                    value = getattr(error, stream, "") or ""
                    if isinstance(value, bytes):
                        value = value.decode(errors="replace")
                    (out / "raw" / (name + "." + stream + ".txt")).write_text(value)
                entry["returncode"] = getattr(error, "returncode", None)
                raise
            entry["returncode"] = result.returncode
            stdout = out / "raw" / (name + ".stdout.txt")
            stderr = out / "raw" / (name + ".stderr.txt")
            stdout.write_text(result.stdout)
            stderr.write_text(result.stderr)
            require(not result.stderr.strip(), "unexpected simulator stderr")
            parsed = parse_output(result.stdout, tasks, cost)
            if cost == 0:
                require([(m["start"], m["completion"]) for m in parsed["tasks"]]
                        == tick_oracle(tasks, policy, quantum), "independent zero-cost oracle mismatch")
            records.append({"workload": workload, "policy": policy, "quantum": quantum,
                            "context_cost": cost, "returncode": 0,
                            "cohort": "finite-postponement" if workload in PREFIX_STUDIES else "policy-comparison",
                            "prefix_metrics": prefix_metrics(parsed, PREFIX_STUDIES[workload]["horizon"]) if workload in PREFIX_STUDIES else None,
                            "stdout_sha256": sha256(stdout), "stderr_sha256": sha256(stderr), **parsed})
            metadata["completed_cases"] = len(records)
            save()
        require(len(records) == 116, "incomplete experiment matrix")
        require(sha256(binary) == binary_hash, "binary changed during experiments")
        require(all(sha256(ROOT / p) == digest for p, digest in source_hashes.items()), "source changed during experiments")
        require(all(sha256(workload_paths[name]) == value["sha256"] for name, value in metadata["workloads"].items()), "workload changed during experiments")
        write_analysis(records, out / "analysis")
        metadata["status"] = "complete"
        metadata["completed_utc"] = now()
        metadata["result_sha256"] = {name: sha256(out / name) for name in (
            "records.json", "analysis/summary.json", "analysis/summary.csv",
            "analysis/policy-comparison.svg", "analysis/round-robin-tradeoff.svg", "analysis/finite-postponement.svg")}
        save()
        print(f"Complete: 116 simulated cases; 74 independent zero-cost oracle comparisons. Results: {out}")
        return 0
    except (Exception, KeyboardInterrupt) as error:
        metadata.update(status="failed", failed_utc=now(), failure={"type": type(error).__name__, "message": str(error)})
        save()
        print(f"Experiment failed; evidence preserved at {out}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
