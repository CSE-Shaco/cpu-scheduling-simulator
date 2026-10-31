# Validation Record

## Scheduling case-study extension

The C11 engine, CLI and public header remain byte-identical to commit `9bba2d6`. The study adds explicit inputs, output validation, analysis and an import-safe wrapper around the unchanged integer-tick oracle algorithm.

- Actual study: 116 complete simulator invocations (84 policy/quantum/cost cases and 32 finite-prefix cases), with continuous timeline, service, waiting/turnaround/response and switching-accounting checks.
- Independent zero-cost oracle: 74 study configurations match per-task first-service and completion times. Nonzero-cost configurations are not claimed to have an independent oracle; their checks include accounting and a hand-derived FCFS cost-1 example.
- Experiment suite: 14 tests pass, including four distinct hand-workload policy outcomes, finite-prefix clipping/termination, SJF/SRTF postponement constructions, corrupt output rejection, failed-run evidence, existing-output protection and exact analysis replay.
- Exact replay: summary JSON/CSV and three SVGs regenerate byte for byte from the recorded input/CLI-output snapshot. SVG XML/numeric geometry checks are separate from rendered visual review.

See [experiment reproduction](../benchmarks/README.md) and the [interpretation report](scheduling-analysis.md). All reported case-study time is abstract simulated time; no elapsed host-performance benchmark is claimed.

## Earlier core verification

Final C11 source verified 2026-10-31 on Darwin arm64 with Apple clang 21.0.0 and Python 3.15.1. Builds and sanitizer artifacts were written to private temporary directories, not the repository.

A separate Release CMake/CTest verification was completed on 2026-10-31 on Darwin arm64 with Homebrew Clang 23.1.4, Python 3.15.1 and temporary CMake 3.31.10. Configuration and build succeeded; all three registered tests passed: `scheduler_correctness`, `scheduler_cli`, and `scheduler_tick_oracle`. The build directory was `/tmp/cpu-scheduling-cmake-release.dVGNRh`, outside the repository. Command output is recorded in `portfolio-management/public-readiness-checks/` in the portfolio workspace.

## Checked-in Test Entry Point

The documented `tests/run_tests.sh` entrypoint was run against a fresh copy of the project source. It uses `cc` (or `CC`) with `-std=c11 -O2 -Wall -Wextra -Wpedantic -Werror`, then runs C assertions, CLI cases, and the independent tick oracle.

```text
PASS 208 C checks (12 hand-derived/edge scenarios plus validation)
PASS 18 CLI validation cases
PASS 200 differential cases against independent tick oracle (zero context cost)
```

The additional CLI cases reject CSV text containing embedded NUL bytes. The previous parser silently truncated such input and accepted hidden trailing fields; it now rejects the input before string parsing. Four regression cases cover the defect. CLI validation also includes malformed fields, duplicate IDs, invalid options and CRLF. The oracle advances one integer tick at a time and compares first-service/completion times with the event-driven engine.

## Sanitizers and Release Assertions

AddressSanitizer and UndefinedBehaviorSanitizer builds passed all 208 C assertions and 18 CLI cases without reported diagnostics. Sanitizer flags were `-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer` with the same warning and error flags as the normal build.

A `-DNDEBUG -O3` build kept all 208 C checks active. A deliberately incorrect fixture exited nonzero as expected, confirming test checks were not compiled away.

## Limits and Unverified Work

The checked-in independent oracle covers zero context-switch cost. The simulator returns deterministic model outcomes, not host execution-time benchmarks; no scheduling speedup or real-kernel behavior is claimed.

CMake/CTest is verified for this configuration and host. The optional CMake build declares C11 targets and registers Python checks when an interpreter is available; this result does not establish behavior on other toolchains or platforms.
