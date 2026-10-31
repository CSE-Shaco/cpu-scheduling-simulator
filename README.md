# CPU Scheduling Simulator

**What I Built:** A C11 single-CPU event-driven simulator for FCFS, SJF, SRTF and Round Robin, including arrivals, preemption, idle intervals, configurable context-switch cost and scheduling metrics.

**How It Works:** One CPU clock advances to an arrival, completion or quantum boundary. The driver admits ready tasks, a scheduler selects a task index, and the engine records a Gantt timeline plus waiting, turnaround and response times.

**What I Verified:** 208 C checks, 18 CLI validation cases, and 200 independent integer-tick comparisons pass. AddressSanitizer and UndefinedBehaviorSanitizer checks pass for the C assertions and CLI. [Executed commands and limits](docs/validation.md).

## Technical Highlights

- Event-driven advancement jumps across idle periods instead of simulating each elapsed tick.
- Explicit task ownership and index-based ready queues prevent duplicated mutable task state.
- Stable tie-breaking and arrivals-before-RR-requeue rules make simultaneous events reproducible.
- Arrivals during context switching affect final dispatch without consuming burst time or charging twice.
- Hand-derived schedules, independent tick simulation and sanitizers provide complementary validation.

## Core Technical Challenges

Arrival, completion and quantum-expiry events can coincide. The [event rules](docs/semantics.md) define admission order, tie-breaking and context-switch accounting explicitly. All components use one clock and one remaining-service store so dispatch and completion cannot observe divergent copies of task state.

## Architecture

```text
include/scheduler.h     C API, task/options and result ownership contract
src/simulator.c         Task state, CPU clock, driver, scheduler and ready queue
src/main.c              CSV input, command-line options and text/CSV output
tests/                  C assertions, CLI validation and independent tick oracle
workloads/              Explicit-arrival CSV examples
docs/                   Event semantics, implementation decisions and validation
```

`Task` inputs are borrowed and immutable. Internal `TaskState` records own remaining service; `ReadyQueue` stores task indices. `CPU` owns time, `Driver` coordinates execution, and a `Scheduler` function pointer selects a ready entry. `SimResult` owns output buffers and is released with `sim_result_free()`. [Implementation details](docs/implementation.md).

## Implementation Decisions

- Use signed 64-bit abstract time and reject time overflow.
- Use linear ready-set selection and an index array for inspectable behavior; no optimal ready-queue complexity is claimed.
- Admit arrivals through the end of a context switch before selecting its final target; charge that transition once.
- Use explicit `id,arrival,burst` CSV, with separate execution options for quantum and switch cost.
- Return metrics and timeline as data so tests can verify accounting without parsing console output.

## Build & Run

Requires a C11 compiler. Python 3 is used only for CLI/oracle tests. From this repository root:

```sh
sh tests/run_tests.sh
./build/scheduler_c workloads/example.csv --policy srtf
./build/scheduler_c workloads/example.csv --policy rr --quantum 2 --context-switch 1
```

For a production-only build:

```sh
mkdir -p build
cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Iinclude \
  src/simulator.c src/main.c -o build/scheduler_c
```

Optional CMake configuration builds C11 targets and registers Python checks when an interpreter is available:

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
```

CMake execution is **Not Verified** because CMake is unavailable in the current environment. Direct compiler builds were executed after the final layout change. Generated files are ignored under `build/`.

Input is strict unquoted CSV `id,arrival,burst`, with an optional header. IDs use letters, digits, `_` or `-`; `IDLE` and `SWITCH` are reserved. Arrival must be nonnegative, burst positive and IDs unique. Empty input, blank lines, `#` comments and CRLF are supported. The CLI limits IDs to 63 bytes and uses a 512-byte input-line buffer; quoted fields and whitespace normalization are outside scope.

## Testing & Verification

The C assertion suite checks hand-derived/edge scenarios and invalid input/overflow. CLI tests include embedded-NUL rejection, malformed fields and invalid options. A separately written tick-by-tick oracle uses a different time-advancement approach to compare completion and first-service times. See [validation](docs/validation.md) for executed counts and sanitizer scope.

## Results & Limitations

For `A=(0,8), B=(1,4), C=(2,2)` with zero switch cost:

| Policy | Completion A | Completion B | Completion C | Average waiting |
|---|---:|---:|---:|---:|
| FCFS | 8 | 12 | 14 | 5.667 |
| SJF | 8 | 14 | 10 | 5.000 |
| SRTF | 14 | 7 | 4 | 2.667 |
| RR, quantum 2 | 14 | 10 | 6 | 4.333 |

These are deterministic simulated outcomes, not host performance measurements or universal scheduler rankings. The model has one CPU and CPU bursts only, without I/O blocking, priority aging, multicore affinity or real kernel interrupts. Context cost is an abstract constant. Very small RR quanta can still produce many events. Independent oracle coverage is limited to zero-cost switching; nonzero costs use hand-derived cases.

No performance speedup or real-kernel behavior is claimed. No license or remote repository was added. [Project review status](docs/provenance.md).
