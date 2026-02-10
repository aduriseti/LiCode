import unittest
import asyncio
import json
import os
import shutil
import tempfile
import time
import io
from unittest.mock import MagicMock, patch, AsyncMock
from market.runner import MarketRunner
from market.orchestrator import AgentAction
from market.core.state import MarketState

class IntegrationDashboardTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a temp directory for the arena
        self.test_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir)

    @patch('market.runner.Shark')
    @patch('market.runner.socket.create_connection')
    @patch('market.runner.subprocess.Popen')
    async def test_integration_flow_with_json_logs(self, MockPopen, MockSocket, MockShark):
        """
        Tests the integration between MarketRunner and the Dashboard's expected input (JSON logs).
        Mocks LLM (Shark) and OpenCode server.
        """
        # 1. Setup Mock Server
        MockSocket.return_value.__enter__.return_value = MagicMock()
        MockPopen.return_value.poll.return_value = None
        
        # 2. Setup Mock Shark (The LLM)
        # Agent 0 will propose a verifier that fails Agent 1
        agent_0_action = AgentAction(
            agent_id="agent_0",
            beliefs={"agent_0_cand": 0.9, "agent_1_cand": 0.1},
            proposals=[{
                "type": "VERIFIER",
                "files": {
                    "run.sh": "#!/bin/bash\\nexit 1", 
                    "test.py": "print('fail')"
                }
            }]
        )
        # Agent 1 will just bet
        agent_1_action = AgentAction(
            agent_id="agent_1",
            beliefs={"agent_0_cand": 0.5, "agent_1_cand": 0.5}
        )

        shark_0 = MagicMock()
        shark_0.get_action = AsyncMock(return_value=agent_0_action)
        shark_0.initialize_session = AsyncMock()
        shark_0.agent_id = "agent_0"
        shark_0.session = MagicMock()
        shark_0.session.id = "ses_mock_0"

        shark_1 = MagicMock()
        shark_1.get_action = AsyncMock(return_value=agent_1_action)
        shark_1.initialize_session = AsyncMock()
        shark_1.agent_id = "agent_1"
        shark_1.session = MagicMock()
        shark_1.session.id = "ses_mock_1"

        # MockShark side_effect to return our mocks
        MockShark.side_effect = [shark_0, shark_1]

        # 3. Run the Tournament
        runner = MarketRunner(
            prompt="Implement Fibonacci",
            n_agents=2,
            budget=100.0,
            api_url="http://127.0.0.1"
        )

        # Intercept stdout to capture JSON logs
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            await runner.run_loop(max_rounds=1, stream_ui=False, json_logs=True)
            output = mock_stdout.getvalue()
            
            # 4. Verify JSON Logs (This is what the Dashboard plugin reads)
            json_events = []
            for line in output.split('\n'):
                if line.strip():
                    try:
                        json_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            # We expect state updates, logs, etc.
            self.assertTrue(any(e.get('type') == 'state' for e in json_events))
            self.assertTrue(any(e.get('type') == 'log' for e in json_events))
            self.assertTrue(any(e.get('type') == 'agent_init' for e in json_events))
            
            # Find a state event and check its content
            state_event = next(e for e in json_events if e.get('type') == 'state')
            self.assertIn('round', state_event)
            self.assertIn('whale_wealth', state_event)
            self.assertIn('assets', state_event)
            
            # Verify the verifier was created in the orchestrator
            self.assertEqual(len(runner.orchestrator.state.assets), 3)

if __name__ == '__main__':
    unittest.main()