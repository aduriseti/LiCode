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
        shark_0.close = AsyncMock()

        shark_1 = MagicMock()
        shark_1.get_action = AsyncMock(return_value=agent_1_action)
        shark_1.initialize_session = AsyncMock()
        shark_1.agent_id = "agent_1"
        shark_1.session = MagicMock()
        shark_1.session.id = "ses_mock_1"
        shark_1.close = AsyncMock()

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
            await runner.initialize(json_logs=True)
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
            self.assertIn('round_num', state_event)
            self.assertIn('whale_wealth', state_event)
            self.assertIn('assets', state_event)
            
            # Verify the verifier was created in the orchestrator
            self.assertEqual(len(runner.orchestrator.state.assets), 3)

    @patch('market.runner.socket.create_connection')
    @patch('market.runner.subprocess.Popen')
    @patch('market.agents.shark.AsyncOpencode')
    async def test_recovery_from_malformed_llm_json(self, MockClient, MockPopen, MockSocket):
        """
        Integration test verifying that the runner survives an agent returning non-JSON initially.
        """
        MockSocket.return_value.__enter__.return_value = MagicMock()
        MockPopen.return_value.poll.return_value = None
        
        # Setup Mock Client
        mock_client_inst = MockClient.return_value
        mock_client_inst.session.create = AsyncMock(return_value=MagicMock(id="ses_123"))
        mock_client_inst.close = AsyncMock()
        
        # Responses: 
        # Shark 0 (R1): bad, then good (retry)
        # Shark 1 (R1): good
        res_0_bad = MagicMock(text="blabber")
        res_0_good = MagicMock(text='{"beliefs": {"cand_0": 0.9}, "proposals": []}')
        res_1_good = MagicMock(text='{"beliefs": {}, "proposals": []}')
        
        mock_client_inst.session.chat = AsyncMock(side_effect=[res_0_bad, res_0_good, res_1_good])

        runner = MarketRunner(prompt="Test", n_agents=2, budget=100.0)
        await runner.initialize(json_logs=True)
        
        # Run 1 round.
        # We need to patch tenacity wait to avoid delay
        with patch('tenacity.nap.time.sleep'):
            await runner.run_loop(max_rounds=1, stream_ui=False, json_logs=True)
        
        self.assertEqual(runner.orchestrator.state.round_num, 1)
        # 3 calls to chat: 2 for shark 0 (fail+retry), 1 for shark 1
        self.assertEqual(mock_client_inst.session.chat.call_count, 3)

if __name__ == '__main__':
    unittest.main()