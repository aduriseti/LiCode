import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from market.cli import main
import sys
import io
import logging
import os
import json
import pytest

class TestCLI(unittest.TestCase):
    
    def setUp(self):
        self.patcher = patch('market.cli.validate_config_with_api', new_callable=AsyncMock)
        self.mock_validate = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    @pytest.mark.timeout(10)
    @patch('market.cli.MarketRunner')
    @patch('market.cli.Orchestrator')
    def test_run_command(self, MockOrch, MockRunner):
        # Setup mocks
        mock_runner_instance = MockRunner.return_value
        
        # Use AsyncMock for coroutines
        from unittest.mock import AsyncMock
        mock_runner_instance.run_loop = AsyncMock()
        mock_runner_instance.initialize = AsyncMock()
        mock_runner_instance.close = AsyncMock()
        
        mock_runner_instance.orchestrator.state.to_json.return_value = "{}"
        mock_runner_instance.orchestrator.get_final_report.return_value = "Report"
        
        # Args
        test_args = ["cli.py", "run", "--prompt", "foo", "--rounds", "5"]
        with patch.object(sys, 'argv', test_args):
            main()
            
        # Verify MarketRunner initialized correctly
        MockRunner.assert_called_with(
            "foo", 3, 1000.0, None, 
            model=["gemini-3-flash", "claude-sonnet-4-6", "glm-5"], provider=["opencode"], 
            agent_timeout=120.0, dashboard=False,
            max_retries=2, initial_backoff=120.0, max_backoff=1000.0
        )
        
        # Verify loop called
        mock_runner_instance.run_loop.assert_called_with(5, stream_ui=True, json_logs=False)
        
        # Verify loop called
        mock_runner_instance.run_loop.assert_called_with(5, stream_ui=True, json_logs=False)

    @pytest.mark.timeout(10)
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

    @pytest.mark.timeout(10)
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

    @pytest.mark.timeout(10)
    @patch('market.cli.MarketRunner')
    def test_log_level_after_subcommand(self, MockRunner):
        """Verifies that --log-level works after the subcommand (regression case)."""
        from unittest.mock import AsyncMock
        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.run_loop = AsyncMock()
        mock_runner_instance.initialize = AsyncMock()
        mock_runner_instance.close = AsyncMock()
        mock_runner_instance.orchestrator.state.to_json.return_value = "{}"
        mock_runner_instance.orchestrator.get_final_report.return_value = "Report"
        
        # Use a fresh logger level for each test to avoid interference
        logging.getLogger().setLevel(logging.WARNING)
        test_args = ["cli.py", "run", "--prompt", "test", "--log-level", "DEBUG"]
        with patch.object(sys, 'argv', test_args):
            with patch('sys.stderr', new=io.StringIO()):
                main()
            self.assertEqual(logging.getLogger().level, logging.DEBUG)

    @pytest.mark.timeout(10)
    @patch('market.cli.MarketRunner')
    def test_log_level_before_subcommand(self, MockRunner):
        """Verifies that --log-level works before the subcommand (global case)."""
        from unittest.mock import AsyncMock
        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.run_loop = AsyncMock()
        mock_runner_instance.initialize = AsyncMock()
        mock_runner_instance.close = AsyncMock()
        mock_runner_instance.orchestrator.state.to_json.return_value = "{}"
        mock_runner_instance.orchestrator.get_final_report.return_value = "Report"
        
        # Use a fresh logger level for each test to avoid interference
        logging.getLogger().setLevel(logging.WARNING)
        test_args = ["cli.py", "--log-level", "ERROR", "run", "--prompt", "test"]
        with patch.object(sys, 'argv', test_args):
            with patch('sys.stderr', new=io.StringIO()):
                main()
            self.assertEqual(logging.getLogger().level, logging.ERROR)

    @pytest.mark.timeout(10)
    @patch('market.cli.MarketRunner')
    def test_dashboard_url_dual_output(self, MockRunner):
        """Verifies that Dashboard URL hits both stdout (JSON) and stderr (Text) when json_logs=True."""
        mock_runner_instance = MockRunner.return_value
        mock_runner_instance.run_loop = AsyncMock()
        mock_runner_instance.close = AsyncMock()
        
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

class TestCLIAPIValidation(unittest.IsolatedAsyncioTestCase):
    @pytest.mark.timeout(10)
    async def test_ephemeral_validation_valid(self):
        """Verifies that the ephemeral server logic works for valid configs."""
        from market.cli import validate_config_with_api, MarketArgumentParser
        import argparse
        
        args = argparse.Namespace(
            api_url=None, # Should trigger ephemeral server
            provider=["opencode"],
            model=["gemini-3-flash"]
        )
        parser = MarketArgumentParser()
        
        try:
            # This will now spawn a real 'npx opencode serve' in the background
            await validate_config_with_api(args, parser)
        except SystemExit:
            self.fail("validate_config_with_api raised SystemExit unexpectedly on valid model.")

    @pytest.mark.timeout(10)
    async def test_ephemeral_validation_invalid_model(self):
        """Verifies that suggestions work correctly with the ephemeral server."""
        from market.cli import validate_config_with_api, MarketArgumentParser
        import argparse
        
        args = argparse.Namespace(
            api_url=None,
            provider=["opencode"],
            model=["gemini-3-flas"] # Typo
        )
        parser = MarketArgumentParser()
        
        stderr_capture = io.StringIO()
        with patch('sys.stderr', stderr_capture):
            with patch('sys.stdout', new=io.StringIO()):
                with self.assertRaises(SystemExit):
                    await validate_config_with_api(args, parser)
        
        output = stderr_capture.getvalue()
        self.assertIn("Did you mean: gemini-3-flash", output)

    @pytest.mark.timeout(10)
    async def test_live_valid_model(self):
        """Verifies that gemini-3-flash validates correctly against the real OpenCode API."""
        from market.cli import validate_config_with_api, MarketArgumentParser
        import argparse
        
        args = argparse.Namespace(
            api_url=os.environ.get("OPENCODE_API_URL", "http://127.0.0.1:4096"),
            provider=["opencode"],
            model=["gemini-3-flash"]
        )
        parser = MarketArgumentParser()
        
        # If the API is running, this should not raise an error.
        # If the API is not running, it will just warn and return (which also passes).
        try:
            await validate_config_with_api(args, parser)
        except SystemExit:
            self.fail("validate_config_with_api raised SystemExit unexpectedly on valid model.")

    @pytest.mark.timeout(10)
    async def test_live_invalid_model_suggestion(self):
        """Verifies that an invalid model yields a suggestion."""
        from market.cli import validate_config_with_api, MarketArgumentParser
        import argparse
        
        args = argparse.Namespace(
            api_url=os.environ.get("OPENCODE_API_URL", "http://127.0.0.1:4096"),
            provider=["opencode"],
            model=["gemini-3-flas"]  # Intentionally misspelled
        )
        parser = MarketArgumentParser()
        
        # We need to catch SystemExit and inspect the stderr/stdout
        stderr_capture = io.StringIO()
        with patch('sys.stderr', stderr_capture):
            with patch('sys.stdout', new=io.StringIO()): # Prevent JSON errors dumping to console during test
                with self.assertRaises(SystemExit):
                    await validate_config_with_api(args, parser)
        
        output = stderr_capture.getvalue()
        # If API was down, it would just return without SystemExit. 
        # But if it raised SystemExit, it must be because the validation failed.
        # We verify that our new difflib suggestion logic works.
        self.assertIn("Did you mean:", output)
        self.assertIn("gemini-3-flash", output)

    @pytest.mark.timeout(10)
    async def test_live_invalid_provider_suggestion(self):
        """Verifies that an invalid provider yields a suggestion and available list."""
        from market.cli import validate_config_with_api, MarketArgumentParser
        import argparse
        
        args = argparse.Namespace(
            api_url=os.environ.get("OPENCODE_API_URL", "http://127.0.0.1:4096"),
            provider=["opencod"], # Intentionally misspelled
            model=["gemini-3-flash"]
        )
        parser = MarketArgumentParser()
        
        stderr_capture = io.StringIO()
        with patch('sys.stderr', stderr_capture):
            with patch('sys.stdout', new=io.StringIO()):
                with self.assertRaises(SystemExit):
                    await validate_config_with_api(args, parser)
        
        output = stderr_capture.getvalue()
        self.assertIn("Did you mean: opencode", output)
        self.assertIn("Available:", output)

    @pytest.mark.timeout(10)
    async def test_live_invalid_provider_in_model_string_suggestion(self):
        """Verifies that an invalid provider in a model string yields a suggestion and available list."""
        from market.cli import validate_config_with_api, MarketArgumentParser
        import argparse
        
        args = argparse.Namespace(
            api_url=os.environ.get("OPENCODE_API_URL", "http://127.0.0.1:4096"),
            provider=["opencode"],
            model=["opencod/gemini-3-flash"] # Intentionally misspelled provider part
        )
        parser = MarketArgumentParser()
        
        stderr_capture = io.StringIO()
        with patch('sys.stderr', stderr_capture):
            with patch('sys.stdout', new=io.StringIO()):
                with self.assertRaises(SystemExit):
                    await validate_config_with_api(args, parser)
        
        output = stderr_capture.getvalue()
        self.assertIn("Did you mean: opencode", output)
        self.assertIn("Available:", output)

if __name__ == '__main__':
    unittest.main()
