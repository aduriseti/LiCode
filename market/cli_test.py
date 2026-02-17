import unittest
from unittest.mock import patch, MagicMock
from market.cli import main
import sys

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
        MockRunner.assert_called_with("foo", 3, 1000.0, "http://127.0.0.1:4096", model="gemini-3-flash", provider="opencode", agent_timeout=300.0)
        
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

if __name__ == '__main__':
    unittest.main()
