"""Experiment protocol and independent hand/oracle checks; no host speed claims."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
import experiment_data as data
import run_experiments as runner

BINARY = None

FCFS = """Gantt (half-open intervals)
[0,8) A
[8,12) B
[12,14) C
id,arrival,burst,start,completion,waiting,turnaround,response
A,0,8,0,8,0,8,0
B,1,4,8,12,7,11,7
C,2,2,12,14,10,12,10
makespan=14 busy=14 idle=0 switching=0 context_switches=2 average_waiting=5.667 average_turnaround=10.333
"""
TASKS = [("A", 0, 8), ("B", 1, 4), ("C", 2, 2)]


class ParserTests(unittest.TestCase):
    def test_hand_derived_fcfs_and_exact_averages(self):
        result = data.parse_output(FCFS, TASKS, 0)
        self.assertEqual(result["metrics"]["average_waiting"], 17 / 3)
        self.assertEqual(result["metrics"]["average_response"], 17 / 3)
        self.assertEqual(result["metrics"]["productive_utilization_percent"], 100)

    def test_gap_and_excess_service_rejected(self):
        for text in (FCFS.replace("[8,12)", "[9,12)"), FCFS.replace("[0,8)", "[0,9)")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                data.parse_output(text, TASKS, 0)

    def test_corrupt_metrics_and_rounded_summary_rejected(self):
        for text in (FCFS.replace("B,1,4,8,12,7,11,7", "B,1,4,8,12,8,11,7"),
                     FCFS.replace("average_waiting=5.667", "average_waiting=5.668"),
                     FCFS.replace("context_switches=2", "context_switches=1"),
                     FCFS.replace("busy=14", "busy=13")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                data.parse_output(text, TASKS, 0)

    def test_early_service_and_extra_output_rejected(self):
        for text in (FCFS.replace("[0,8) A", "[0,8) C"), FCFS + "extra\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                data.parse_output(text, TASKS, 0)

    def test_malformed_workload_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.csv"
            for content in ("id,arrival,burst\nA,0,1\nA,1,2\n", "id,arrival,burst\nA,0,0\n", "id,arrival,burst\nIDLE,0,1\n"):
                path.write_text(content)
                with self.subTest(content=content), self.assertRaises(ValueError):
                    data.load_tasks(path)

    def test_prefix_clips_service_and_stops_ready_gap_at_completion(self):
        parsed = {"tasks": [{"id": "LONG", "arrival": 0, "start": 0, "completion": 6, "waiting": 2}],
                  "timeline": [{"task": "LONG", "start": 0, "end": 2},
                               {"task": "OTHER", "start": 2, "end": 4},
                               {"task": "LONG", "start": 4, "end": 6},
                               {"task": "OTHER", "start": 6, "end": 20}]}
        metrics = data.prefix_metrics(parsed, 10)
        self.assertEqual(metrics["long_service_before_horizon"], 4)
        self.assertEqual(metrics["long_max_ready_gap_before_horizon"], 2)
        self.assertTrue(metrics["long_done_by_horizon"])
        self.assertTrue(data.prefix_metrics(parsed, 6)["long_done_by_horizon"])
        self.assertEqual(data.prefix_metrics(parsed, 1)["long_service_before_horizon"], 1)


class FailurePreservationTests(unittest.TestCase):
    def test_existing_output_refused_without_touching_it(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            binary = directory / "scheduler"
            binary.write_text("synthetic test binary\n")
            binary.chmod(0o700)
            out = directory / "out"
            out.mkdir()
            marker = out / "keep.txt"
            marker.write_text("preserve")
            with self.assertRaises(SystemExit) as error:
                runner.main(["--binary", str(binary), "--out", str(out), "--build-command", "synthetic unit fixture"])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(marker.read_text(), "preserve")

    def test_failed_command_retains_failed_record_and_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            binary = directory / "scheduler"
            binary.write_text("synthetic test binary\n")
            binary.chmod(0o700)
            out = directory / "out"
            version = subprocess.CompletedProcess([], 0, "synthetic compiler\n", "")
            failure = subprocess.CalledProcessError(7, [str(binary)], output="partial\n", stderr="intentional test failure\n")
            with patch.object(runner.platform, "platform", return_value="synthetic-unit-host"), \
                 patch.object(runner.platform, "python_version", return_value="synthetic-python"), \
                 patch.object(runner.subprocess, "run", side_effect=[version, failure]):
                status = runner.main(["--binary", str(binary), "--out", str(out), "--build-command", "synthetic unit fixture"])
            self.assertEqual(status, 1)
            metadata = json.loads((out / "metadata.json").read_text())
            self.assertEqual(metadata["status"], "failed")
            self.assertEqual(metadata["commands"][0]["returncode"], 7)
            self.assertEqual(json.loads((out / "records.json").read_text()), [])
            self.assertEqual(next((out / "raw").glob("*.stderr.txt")).read_text(), "intentional test failure\n")
            with self.assertRaises(ValueError):
                data.load_run(out)


@unittest.skipUnless(BINARY, "provide scheduler_c executable to run native integration checks")
class NativeExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        cls.output_path = cls.folder / "complete"
        result = runner.main(["--binary", str(BINARY), "--out", str(cls.output_path),
                              "--build-command", "native integration executable supplied by test runner"])
        if result:
            raise AssertionError("native experiment execution failed")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_full_matrix_and_zero_cost_oracle(self):
        metadata, records = data.load_run(self.output_path)
        self.assertEqual(metadata["completed_cases"], 116)
        self.assertEqual(len(records), 116)
        self.assertEqual(sum(r["context_cost"] == 0 for r in records), 74)
        self.assertEqual(sum(r["cohort"] == "policy-comparison" for r in records), 84)
        self.assertEqual(sum(r["cohort"] == "finite-postponement" for r in records), 32)
        self.assertTrue(all(r["metrics"]["busy"] == sum(t["burst"] for t in r["tasks"]) for r in records))

    def test_hand_derived_switch_cost_and_preemptive_results(self):
        path = self.folder / "hand.csv"
        path.write_text("id,arrival,burst\nA,0,8\nB,1,4\nC,2,2\n")
        cases = [("fcfs", 2, 0, [8, 12, 14], 17 / 3, 14, 2),
                 ("fcfs", 2, 1, [8, 13, 16], 20 / 3, 16, 2),
                 ("sjf", 2, 0, [8, 14, 10], 5, 14, 2),
                 ("srtf", 2, 0, [14, 7, 4], 8 / 3, 14, 4),
                 ("rr", 2, 0, [14, 10, 6], 13 / 3, 14, 5)]
        zero_cost_outcomes = set()
        for policy, quantum, cost, ends, waiting, makespan, switches in cases:
            with self.subTest(policy=policy, cost=cost):
                r = subprocess.run([str(BINARY), str(path), "--policy", policy, "--quantum", str(quantum),
                                    "--context-switch", str(cost)], text=True, capture_output=True, check=True, timeout=5)
                parsed = data.parse_output(r.stdout, TASKS, cost)
                self.assertEqual([m["completion"] for m in parsed["tasks"]], ends)
                self.assertEqual(parsed["metrics"]["average_waiting"], waiting)
                self.assertEqual(parsed["metrics"]["makespan"], makespan)
                self.assertEqual(parsed["metrics"]["context_switches"], switches)
                if cost == 0:
                    zero_cost_outcomes.add(tuple(m["completion"] for m in parsed["tasks"]))
        self.assertEqual(len(zero_cost_outcomes), 4)

    def test_finite_prefix_postponement_and_response_blindspot(self):
        _, records = data.load_run(self.output_path)
        for horizon in (16, 32, 64, 128):
            for family in ("ready-short-stream", "late-short-stream"):
                study = {r["policy"]: r for r in records if r["workload"] == f"{family}-h{horizon:03d}"}
                for r in study.values():
                    self.assertEqual(r["metrics"]["makespan"], horizon + 64)
                    self.assertEqual(r["metrics"]["idle"], 0)
                if family == "ready-short-stream":
                    for policy in ("sjf", "srtf"):
                        m = study[policy]["prefix_metrics"]
                        self.assertEqual(m["long_first_start"], horizon)
                        self.assertEqual(m["long_service_before_horizon"], 0)
                        self.assertEqual(m["long_max_ready_gap_before_horizon"], horizon)
                        self.assertEqual(m["long_completion"], horizon + 64)
                else:
                    m = study["srtf"]["prefix_metrics"]
                    self.assertEqual(m["long_first_start"], 0)
                    self.assertEqual(m["long_service_before_horizon"], 1)
                    self.assertEqual(m["long_max_ready_gap_before_horizon"], horizon - 1)
                    self.assertEqual(m["long_waiting"], horizon)
                    for policy in ("fcfs", "sjf"):
                        self.assertEqual(study[policy]["prefix_metrics"]["long_max_ready_gap_before_horizon"], 0)
                        self.assertEqual(study[policy]["prefix_metrics"]["long_completion"], 64)
                self.assertGreater(study["rr"]["prefix_metrics"]["long_service_before_horizon"], 0)

    def test_reanalysis_is_deterministic(self):
        _, records = data.load_run(self.output_path)
        out = self.folder / "reanalysis"
        data.write_analysis(records, out)
        for name in ("summary.json", "summary.csv", "policy-comparison.svg", "round-robin-tradeoff.svg", "finite-postponement.svg"):
            self.assertEqual((out / name).read_bytes(), (self.output_path / "analysis" / name).read_bytes())
        with self.assertRaises(FileExistsError):
            data.write_analysis(records, out)

    def test_analyzer_refuses_output_inside_recorded_input(self):
        output = self.output_path / "do-not-create"
        result = subprocess.run([sys.executable, str(ROOT / "benchmarks/analyze_results.py"),
                                 str(self.output_path), "--out", str(output)],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())

    def test_raw_metric_corruption_rejected_even_with_updated_hashes(self):
        import shutil
        target = self.folder / "corrupt"
        shutil.copytree(self.output_path, target)
        records = json.loads((target / "records.json").read_text())
        record = records[0]
        name = data.case_name(record["workload"], record["policy"], record["quantum"], record["context_cost"])
        stdout = target / "raw" / (name + ".stdout.txt")
        text = stdout.read_text()
        text = text.replace("busy=32", "busy=33")
        self.assertNotEqual(text, stdout.read_text())
        stdout.write_text(text)
        record["stdout_sha256"] = data.sha256(stdout)
        (target / "records.json").write_text(json.dumps(records))
        metadata = json.loads((target / "metadata.json").read_text())
        metadata["result_sha256"]["records.json"] = data.sha256(target / "records.json")
        (target / "metadata.json").write_text(json.dumps(metadata))
        with self.assertRaises(ValueError):
            data.load_run(target)


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        BINARY = Path(sys.argv.pop(1)).resolve()
        # The decorator ran before command-line parsing; enable only these tests.
        NativeExperimentTests.__unittest_skip__ = False
    unittest.main()
