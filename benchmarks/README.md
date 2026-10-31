# Reproducible Scheduling Case Studies

These experiments compare **simulated policy outcomes**, not the wall-clock performance of the C program. The selected algorithms are FCFS, SJF, SRTF and Round Robin. They share a validated event engine but apply different selection, preemption and slice rules.

- Base cohort: six explicit workloads × seven configurations (FCFS, SJF, SRTF, RR q=1/2/4/8) × context cost 0/1 = **84 cases**.
- Finite-prefix cohort: two short-stream families × four horizons × four algorithms (RR q=2) × zero context cost = **32 cases**.
- Total: **116 complete simulated executions**, including **74 independent zero-cost tick-oracle comparisons**.

Read the [analysis report](../docs/scheduling-analysis.md) for convoy behavior, first-response/turnaround tradeoffs, quantum overhead, long-job progress and the limits of finite starvation examples. [Recorded results](results/policy-study-2026-10-31/README.md) include all outcomes, including policy ties and unfavorable cases.

## Run

From the repository root, build the actual CLI and record the command used:

```sh
mkdir -p build
cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Iinclude \
  src/simulator.c src/main.c -o build/scheduler_c

python3 benchmarks/run_experiments.py \
  --binary build/scheduler_c \
  --compiler cc \
  --build-command 'cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Iinclude src/simulator.c src/main.c -o build/scheduler_c' \
  --out benchmarks/results/local-policy-study-01
```

The build-command text is operator-supplied provenance, not independently inferred from the binary. The runner hashes the executable, measured C source, experiment tools, oracle and workloads, records the compiler-version probe and actual CLI commands, and checks that sources/inputs/binary did not change during the run.

Choose a new output directory each time. Existing paths are refused. A command or validation failure retains `status: failed`, partial records and captured output; it is not a successful study. `local*` result directories and `build/` are ignored by Git.

## Record Structure

```text
metadata.json             status, workload snapshots, hashes, host/build and commands
records.json              per-case tasks, full timeline, metrics and prefix observations
raw/                      stdout/stderr from all 116 CLI invocations
analysis/summary.json     precise derived metric values
analysis/summary.csv      116 rows; abstract time, percentages and prefix metrics
analysis/*.svg            policy, quantum and finite-prefix comparisons
```

`metadata.json` embeds the exact UTF-8 CSV text as well as its digest so the input snapshot remains inspectable if a later checkout changes a workload. Average waiting/turnaround/response are recomputed from integer process metrics; the CLI's three-decimal averages are checked but not used as the precise source for analysis. Productive utilization is busy/makespan from time zero, including initial idle and switching in makespan.

## Revalidate and Regenerate

```sh
python3 benchmarks/analyze_results.py \
  benchmarks/results/policy-study-2026-10-31 \
  --out benchmarks/results/local-reanalysis-01
```

This checks complete status, all configuration/command records, embedded input snapshots, output digests, raw trace/metric agreement, and the zero-cost oracle before writing a new derived directory. It refuses to overwrite an existing path or write inside the recorded input directory. The supplied run regenerates the summary JSON/CSV and all three SVGs byte for byte.

The parser checks continuous half-open intervals, exact per-task service, execution after arrival, first/last service times, metric identities, no idle with pending work, and busy+idle+switching=makespan. Context-switch counts agree with the trace and cost. These checks do not replace an independent algorithm oracle for nonzero switching cost.

## Workload Definitions

| Workload | Controlled feature |
| --- | --- |
| `convoy` | Long job first in input, all jobs ready at zero |
| `staggered` | Shorter jobs arrive during a long job's execution |
| `idle-gaps` | Initial and later gaps with no ready work |
| `equal-bursts` | Stable ordering for equal bursts/arrivals |
| `bursty` | Groups of arrivals; each process still has one CPU burst |
| `mixed-bounded` | Eight fixed, varied arrivals and burst lengths |
| `ready-short-stream-h*` | LONG=(0,64), H one-unit jobs at 0..H−1 |
| `late-short-stream-h*` | LONG=(0,64), H one-unit jobs at 1..H |

H takes 16,32,64,128. CSVs are explicit independent synthetic constructions with no random seed or external trace. The short-stream generation recipe is LONG first, then `S000` through `S(H−1)` in arrival order; arrival is `i` or `i+1`, burst is 1. The engine runs the full finite workload; [0,H) metrics are derived afterwards, without a new stop-at-horizon mode.

Tests:

```sh
python3 tests/test_experiments.py build/scheduler_c
```

The same suite is registered as `scheduler_experiments` in CTest and included in `tests/run_tests.sh`.
