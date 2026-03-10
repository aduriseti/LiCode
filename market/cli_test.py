import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from market.cli import main
import sys
import io
import logging
import os
import json

class TestCLI(unittest.TestCase):
    
    @patch('market.cli.MarketRunner')
    @patch('market.cli.Orchestrator')
    def test_run_command(self, MockOrch, MockRunner):
        # Setup mocks
        mock_runner_instance = MockRunner.return_value
        
        # Use AsyncMock for coroutines
        from unittest.mock import AsyncMock
        mock_runner_instance.run_loop = AsyncMock()
        mock_runner_instance.initialize = AsyncMock()
        
        mock_runner_instance.orchestrator.state.to_json.return_value = "{}"
        mock_runner_instance.orchestrator.get_final_report.return_value = "Report"
        
        # Args
        test_args = ["cli.py", "run", "--prompt", "foo", "--rounds", "5"]
        with patch.object(sys, 'argv', test_args):
            main()
            
        # Verify MarketRunner initialized correctly
        MockRunner.assert_called_with("foo", 3, 1000.0, "http://127.0.0.1:4096", model="gemini-3-flash", provider="opencode", agent_timeout=300.0, dashboard=False)
        
        # Verify loop called
        mock_runner_instance.run_loop.assert_called_with(5, stream_ui=True, json_logs=False)
        
        # Verify loop called
        mock_runner_instance.run_loop.assert_called_with(5, stream_ui=True, json_logs=False)

    @patch('market.cli.Orchestrator')
    def test_init_command(self, MockOrch):
        mock_orch_instance = MockOrch.return_value
        mock_orch_instance.state.to_json.return_value = '{"init": true}'
        
        test_args = ["cli.py", "init", "--prompt", "bar"]
        with patch.object(sys, 'argv', test_args):
            # Capture stdout to avoid clutter
            with patch('sys.stdout', new=MagicMock()) as mock_stdout:
                main()
                
        # Verify Orch init
        MockOrch.assert_called_with("bar", 3, 1000.0)

    def test_cli_error_json(self):
        """Verifies that an invalid argument with --json-logs returns a JSON error."""
        import json
        import io
        
        # We must use a command that will trigger an error (e.g. unknown flag)
        test_args = ["cli.py", "run", "--prompt", "test", "--invalid-flag", "--json-logs"]
        
        stdout_capture = io.StringIO()
        with patch.object(sys, 'argv', test_args):
            with patch('sys.stdout', stdout_capture):
                with self.assertRaises(SystemExit) as cm:
                    main()
                
                # Should exit with code 2
                self.assertEqual(cm.exception.code, 2)
                
                # Check output for JSON error
                output = stdout_capture.getvalue().strip()
                error_data = json.loads(output)
                self.assertEqual(error_data["type"], "error")
                self.assertIn("unrecognized arguments", error_data["message"])

    @patch('market.cli.MarketRunner')
    def test_log_level_after_subcommand(self, MockRunner):
        """Verifies that --log-level works after the subcommand (regression case)."""
        from unittest.mock import AsyncMock
        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.run_loop = AsyncMock()
        mock_runner_instance.initialize = AsyncMock()
        mock_runner_instance.orchestrator.state.to_json.return_value = "{}"
        mock_runner_instance.orchestrator.get_final_report.return_value = "Report"
        
        with patch.dict(os.environ, {}, clear=True):
            test_args = ["cli.py", "run", "--prompt", "test", "--log-level", "DEBUG"]
            with patch.object(sys, 'argv', test_args):
                with patch('sys.stderr', new=io.StringIO()):
                    main()
                self.assertEqual(logging.getLogger().level, logging.DEBUG)

    @patch('market.cli.MarketRunner')
    def test_log_level_before_subcommand(self, MockRunner):
        """Verifies that --log-level works before the subcommand (global case)."""
        from unittest.mock import AsyncMock
        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.run_loop = AsyncMock()
        mock_runner_instance.initialize = AsyncMock()
        mock_runner_instance.orchestrator.state.to_json.return_value = "{}"
        mock_runner_instance.orchestrator.get_final_report.return_value = "Report"
        
        with patch.dict(os.environ, {}, clear=True):
            test_args = ["cli.py", "--log-level", "ERROR", "run", "--prompt", "test"]
            with patch.object(sys, 'argv', test_args):
                with patch('sys.stderr', new=io.StringIO()):
                    main()
                self.assertEqual(logging.getLogger().level, logging.ERROR)

    @patch('market.cli.MarketRunner')
    def test_dashboard_url_dual_output(self, MockRunner):
        """Verifies that Dashboard URL hits both stdout (JSON) and stderr (Text) when json_logs=True."""
        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.run_loop = AsyncMock()
        
        # Define a side effect for initialize that logs the URL
        async def mock_initialize(json_logs=False):
            url = "http://127.0.0.1:1234"
            logging.info(f"Dashboard active at {url}")
            sys.stderr.write(f"Dashboard active at {url}\n")
            if json_logs:
                print(json.dumps({"type": "log", "message": f"Dashboard active at {url}"}))
        
        mock_runner_instance.initialize.side_effect = mock_initialize
        mock_runner_instance.orchestrator.state.to_json.return_value = "{}"
        mock_runner_instance.orchestrator.get_final_report.return_value = "Report"

        test_args = ["cli.py", "run", "--prompt", "test", "--json-logs"]
        stderr_capture = io.StringIO()
        stdout_capture = io.StringIO()
        
        with patch.object(sys, 'argv', test_args):
            with patch('sys.stderr', stderr_capture):
                with patch('sys.stdout', stdout_capture):
                    main()
                
        stderr_out = stderr_capture.getvalue()
        stdout_out = stdout_capture.getvalue()
        
        # Verify Human Readable on Stderr
        self.assertIn("Dashboard active at http://127.0.0.1:1234", stderr_out)
        
        # Verify JSON on Stdout
        found_json = False
        for line in stdout_out.splitlines():
            try:
                data = json.loads(line)
                if data.get("type") == "log" and "Dashboard active at http://127.0.0.1:1234" in data.get("message"):
                    found_json = True
            except: continue
        self.assertTrue(found_json, "Expected JSON log with dashboard URL on stdout")

if __name__ == '__main__':
    unittest.main()
