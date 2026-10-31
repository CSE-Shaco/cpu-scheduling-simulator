"""Independent integer-tick oracle for zero-cost scheduling (new code, no coursework import).

The production engine jumps to events. This test deliberately advances one tick
at a time and compares completion/first-start times for randomized small inputs.
"""
import csv
import io
import pathlib
import random
import subprocess
import sys
import tempfile


def oracle(tasks, policy, quantum):
    remaining = [task[2] for task in tasks]
    starts = [-1] * len(tasks)
    ends = [-1] * len(tasks)
    ready = []
    current = None
    ticks_in_slice = 0
    now = 0
    while any(value > 0 for value in remaining):
        ready.extend(i for i, task in enumerate(tasks) if task[1] == now)
        if current is not None:
            if remaining[current] == 0:
                ends[current] = now
                current = None
            elif policy == 'rr' and ticks_in_slice == quantum:
                ready.append(current)
                current = None
            elif policy == 'srtf':
                ready.append(current)
                current = None
        if current is None and ready:
            if policy in ('sjf', 'srtf'):
                current = min(ready, key=lambda i: (remaining[i], tasks[i][1], i))
                ready.remove(current)
            else:
                current = ready.pop(0)
            ticks_in_slice = 0
        if current is not None:
            if starts[current] < 0:
                starts[current] = now
            remaining[current] -= 1
            ticks_in_slice += 1
        now += 1
    if current is not None:
        ends[current] = now
    return list(zip(starts, ends))


def main():
    exe = str(pathlib.Path(sys.argv[1]).resolve())
    rng = random.Random(41389)
    cases = 0
    with tempfile.TemporaryDirectory() as folder:
        path = pathlib.Path(folder) / 'case.csv'
        for _ in range(50):
            tasks = [(f'P{i}', rng.randrange(12), rng.randrange(1, 9)) for i in range(6)]
            path.write_text(''.join(f'{name},{arrival},{burst}\n' for name, arrival, burst in tasks))
            for policy in ('fcfs', 'sjf', 'srtf', 'rr'):
                quantum = rng.randrange(1, 5)
                expected = oracle(tasks, policy, quantum)
                result = subprocess.run([exe, str(path), '--policy', policy, '--quantum', str(quantum)],
                                        text=True, capture_output=True, timeout=5, check=True)
                metrics = result.stdout.split('id,arrival,burst,start,completion,waiting,turnaround,response\n')[1]
                rows = list(csv.reader(io.StringIO(metrics)))[:len(tasks)]
                actual = [(int(row[3]), int(row[4])) for row in rows]
                assert actual == expected, (tasks, policy, quantum, expected, actual)
                cases += 1
    print(f'PASS {cases} differential cases against independent tick oracle (zero context cost)')


if __name__ == "__main__":
    main()
