import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from importlib.util import module_from_spec, spec_from_file_location


engine_path = Path(__file__).resolve().parent / "Avel Technical Assessment.py"
spec = spec_from_file_location("avel_engine", engine_path)
avel_engine = module_from_spec(spec)
spec.loader.exec_module(avel_engine)
WorkflowEngine = avel_engine.WorkflowEngine


class WorkflowEngineTests(unittest.TestCase):
    def test_retries_then_prepares_and_pauses(self):
        engine = WorkflowEngine(simulate_failure=True)
        engine.run()

        statuses = [entry["status"] for entry in engine.history]
        self.assertIn("FAILED", statuses)
        self.assertIn("RETRY", statuses)
        self.assertEqual(engine.status, "PAUSED")
        self.assertTrue(engine.context["quote_prepared"])
        self.assertNotIn("send", engine.context)

    def test_send_requires_explicit_approval(self):
        engine = WorkflowEngine(simulate_failure=False)
        engine.run()

        with self.assertRaises(RuntimeError):
            engine.send_quote()

        engine.approve("test")
        engine.run()
        self.assertEqual(engine.status, "COMPLETE")
        self.assertTrue(engine.context["send"]["mock"])

    def test_approval_requires_a_prepared_quote(self):
        engine = WorkflowEngine(simulate_failure=False)

        with self.assertRaisesRegex(RuntimeError, "prepared quote"):
            engine.approve("test")

    def test_invalid_state_is_rejected(self):
        data = WorkflowEngine(simulate_failure=False).to_dict()
        data["status"] = []

        with self.assertRaisesRegex(ValueError, "invalid status"):
            WorkflowEngine.from_dict(data)

    def test_malformed_state_json_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "workflow.json"
            state_path.write_text("{invalid", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid workflow state JSON"):
                avel_engine.load_state(state_path)


class WorkflowCliTests(unittest.TestCase):
    def run_cli(self, working_directory, *arguments):
        return subprocess.run(
            [sys.executable, str(engine_path), *map(str, arguments)],
            cwd=working_directory,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_pause_and_approval_persist_across_cli_processes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "workflow.json"

            run_result = self.run_cli(
                temporary_directory,
                "run",
                "--state",
                state_path,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stderr)
            self.assertIn("[PAUSED]", run_result.stdout)
            self.assertIn("Temporary API timeout", run_result.stdout)

            approve_result = self.run_cli(
                temporary_directory,
                "approve",
                "--state",
                state_path,
            )
            self.assertEqual(approve_result.returncode, 0, approve_result.stderr)

            status_result = self.run_cli(
                temporary_directory,
                "status",
                "--state",
                state_path,
            )
            self.assertEqual(status_result.returncode, 0, status_result.stderr)
            self.assertIn("Status: COMPLETE", status_result.stdout)
            self.assertEqual(status_result.stdout.count("[START] Workflow REQ-1042"), 1)

    def test_run_preserves_existing_state_unless_restart_is_requested(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "workflow.json"
            initial_result = self.run_cli(
                temporary_directory,
                "run",
                "--state",
                state_path,
            )
            self.assertEqual(initial_result.returncode, 0, initial_result.stderr)
            original_state = state_path.read_text(encoding="utf-8")

            refused_result = self.run_cli(
                temporary_directory,
                "run",
                "--state",
                state_path,
            )
            self.assertEqual(refused_result.returncode, 2)
            self.assertIn("Use --restart", refused_result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

            restart_result = self.run_cli(
                temporary_directory,
                "run",
                "--no-failure",
                "--restart",
                "--state",
                state_path,
            )
            self.assertEqual(restart_result.returncode, 0, restart_result.stderr)
            history = json.loads(state_path.read_text(encoding="utf-8"))["history"]
            self.assertEqual(history[0]["status"], "START")
            self.assertEqual(sum(entry["status"] == "START" for entry in history), 1)

    def test_default_state_path_is_relative_to_script(self):
        parser = avel_engine.build_parser()
        arguments = parser.parse_args(["status"])
        self.assertEqual(arguments.state, avel_engine.DEFAULT_STATE_PATH)
        self.assertEqual(
            parser.parse_args(["--state", "custom.json", "status"]).state,
            Path("custom.json"),
        )
        self.assertEqual(
            parser.parse_args(["status", "--state", "custom.json"]).state,
            Path("custom.json"),
        )


if __name__ == "__main__":
    unittest.main()
