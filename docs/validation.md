# Validation Record

Final C11 source verified 2026-10-31 on Darwin arm64 with Apple clang 21.0.0 and Python 3.15.1. Builds and sanitizer artifacts were written to private temporary directories, not the repository.

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

CMake/CTest is **Not Verified** because CMake is unavailable. A separate install attempt did not produce a usable CMake binary. The optional CMake build declares C11 targets and registers Python checks when an interpreter is available.
