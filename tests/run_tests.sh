#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Iinclude src/simulator.c tests/test_simulator.c -o build/scheduler_c_tests
./build/scheduler_c_tests
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Iinclude src/simulator.c src/main.c -o build/scheduler_c
python3 tests/test_cli.py ./build/scheduler_c
python3 tests/differential.py ./build/scheduler_c
