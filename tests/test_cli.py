"""Validate CLI boundary handling using isolated temporary input files."""
import pathlib
import subprocess
import sys
import tempfile

exe = str(pathlib.Path(sys.argv[1]).resolve())
with tempfile.TemporaryDirectory() as folder:
    path = pathlib.Path(folder) / 'workload.csv'
    invalid_workloads = [
        'A,0,1,', 'A,0,1,extra', 'A,0,-1', 'A,0,0', 'A,0,1\nA,2,1',
        'A,0', 'A,1x,2', 'A B,0,1',
        'A,0,1\0,extra\n', '\0A,0,1\n', 'A\0hidden,0,1\n',
        '# hidden\0comment\nA,0,1\n',
    ]
    for data in invalid_workloads:
        path.write_text(data)
        assert subprocess.run([exe, str(path)], capture_output=True, timeout=5).returncode != 0, data
    path.write_text('id,arrival,burst\r\nA,0,2\r\nB,1,1\r\n')
    good = subprocess.run([exe, str(path), '--policy', 'rr', '--quantum', '1'], capture_output=True, text=True, timeout=5)
    assert good.returncode == 0, good.stderr
    assert 'A,0,2,0,3,1,3,0' in good.stdout
    assert 'B,1,1,1,2,0,1,0' in good.stdout
    invalid_options = [['--policy','bad'], ['--quantum','0'], ['--context-switch','-1'], ['--policy'], ['--unknown','1']]
    for args in invalid_options:
        assert subprocess.run([exe,str(path),*args],capture_output=True,timeout=5).returncode != 0
print(f'PASS {len(invalid_workloads) + len(invalid_options) + 1} CLI validation cases')
