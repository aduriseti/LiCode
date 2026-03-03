import unittest
from unittest.mock import patch, MagicMock
from market.cli import main
import sys
import io
import logging
import os

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
                self.assertEqual(logging.getLogger("market").level, logging.DEBUG)

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
                self.assertEqual(logging.getLogger("market").level, logging.ERROR)

if __name__ == '__main__':
    unittest.main()
