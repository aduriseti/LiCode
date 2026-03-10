import unittest
import asyncio
import json
import os
import shutil
import tempfile
import time
import io
import sys
from collections import deque
from unittest.mock import MagicMock, patch, AsyncMock
from opencode_ai.types.event_list_response import EventMessagePartUpdated
from opencode_ai.types import TextPart
from market.runner import MarketRunner
from market.orchestrator import AgentAction, Orchestrator
from market.core.state import MarketState, MarketAsset, AgentPortfolio

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
    @patch('market.runner.asyncio.open_connection')
    @patch('market.runner.asyncio.create_subprocess_exec')
    @patch('market.orchestrator.Orchestrator._clone_workspace')
    @patch('market.logic.oracle.Oracle.run_test', return_value="PASS")
    async def test_integration_flow_with_json_logs(self, MockOracle, MockClone, MockExec, MockAsyncSocket, MockSocket, MockShark):
        """
        Tests the integration between MarketRunner and the Dashboard's expected input (JSON logs).
        Mocks LLM (Shark) and OpenCode server.
        """
        # 1. Setup Mock Server
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        MockAsyncSocket.return_value = (MagicMock(), mock_writer)
        
        MockSocket.return_value.__enter__.return_value = MagicMock()
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.poll.return_value = None
        mock_proc.wait = AsyncMock()
        MockExec.return_value = mock_proc
        
        # Mock Clone to just create the dir so checks pass
        async def side_effect_clone(dest):
            os.makedirs(dest, exist_ok=True)
        MockClone.side_effect = side_effect_clone
        
        # 2. Setup Mock Shark (The LLM)
        # Agent 0 will propose a verifier that fails Agent 1
        agent_0_action = AgentAction(
            agent_id="agent_0",
            beliefs={"agent_0_cand": 0.9, "agent_1_cand": 0.1},
            proposals=[{
                "type": "VERIFIER",
                "path": "tests/v1"
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
        shark_0.shutdown = AsyncMock()

        shark_1 = MagicMock()
        shark_1.get_action = AsyncMock(return_value=agent_1_action)
        shark_1.initialize_session = AsyncMock()
        shark_1.agent_id = "agent_1"
        shark_1.session = MagicMock()
        shark_1.session.id = "ses_mock_1"
        shark_1.close = AsyncMock()
        shark_1.shutdown = AsyncMock()
        # MockShark side_effect to return our mocks
        MockShark.side_effect = [shark_0, shark_1]

        # Intercept stdout to capture JSON logs
        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            # 3. Run the Tournament
            runner = MarketRunner(
                prompt="Implement Fibonacci",
                n_agents=2,
                budget=100.0,
                api_url="http://127.0.0.1"
            )
            
            await runner.initialize(json_logs=True)
            
            # Setup verifier files in cand_0 worktree (since agent_0 proposes it)
            # Orchestrator uses cand_{id} derived from agent_{id}
            cand_0_dir = os.path.join(runner.orchestrator.worktrees_dir, "cand_0")
            v1_dir = os.path.join(cand_0_dir, "tests", "v1")
            os.makedirs(v1_dir, exist_ok=True)
            run_sh = os.path.join(v1_dir, "run.sh")
            with open(run_sh, "w") as f:
                f.write("#!/bin/bash\nexit 1")
            os.chmod(run_sh, 0o755)
            
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

    @patch('market.orchestrator.Orchestrator._clone_workspace')
    @patch('market.agents.shark.AsyncOpencode')
    @patch('market.runner.MarketRunner._start_agent_server')
    @patch('market.runner.MarketRunner._find_free_port')
    async def test_recovery_from_malformed_llm_json(self, MockPort, MockServer, MockClient, MockClone):
        """
        Test verifying that the runner survives an agent returning malformed JSON initially.
        """
        MockClone.return_value = None
        MockServer.return_value = MagicMock()
        MockPort.return_value = 1234
        
        # 1. Setup Mock Client with recovery responses
        mock_client_inst = MockClient.return_value
        mock_client_inst.session.create = AsyncMock(return_value=MagicMock(id="ses_123"))
        mock_client_inst.close = AsyncMock()
    
        # Responses content: 
        # Shark 0: bad, then good (retry)
        # Shark 1: good
        contents = ["This is not JSON", '{"beliefs": {"cand_0": 0.5}}', '{"beliefs": {"cand_0": 0.5}}']
        
        def create_mock_cm(content_text):
            mock_event = MagicMock(spec=EventMessagePartUpdated)
            mock_event.properties = MagicMock()
            mock_part = MagicMock(spec=TextPart)
            mock_part.text = content_text
            mock_part.session_id = "ses_123"
            mock_part.id = "p1"
            mock_event.properties.part = mock_part
            
            async def mock_iter():
                yield mock_event
                
            mock_stream = MagicMock()
            mock_stream.parse = AsyncMock(return_value=mock_iter())
            mock_stream.close = AsyncMock()
            # Handle AsyncStream iteration
            mock_stream.__aiter__.side_effect = lambda: mock_iter()
            
            return mock_stream

        # Mock event.list()
        mock_stream = create_mock_cm("") # Generic stream for tracing
        mock_client_inst.event.list = AsyncMock(return_value=mock_stream)

        # Mock session.messages() - needs to return different things for different calls
        msg_contents = deque(contents)
        async def messages_side_effect(*args, **kwargs):
            c = msg_contents.popleft() if msg_contents else contents[-1]
            mock_part = MagicMock(spec=TextPart)
            mock_part.text = c
            mock_msg = MagicMock()
            mock_msg.parts = [mock_part]
            return [mock_msg]
        
        mock_client_inst.session.messages = AsyncMock(side_effect=messages_side_effect)
        
        mock_client_inst.session.chat = AsyncMock()

        # 2. Setup Runner
        runner = MarketRunner(prompt="Test", n_agents=2, budget=100.0)
        
        # 3. Run round with recovery
        # Patch tenacity wait and asyncio sleep
        with patch('tenacity.nap.time.sleep'):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                await runner.initialize(json_logs=True)
                await runner.run_loop(max_rounds=1, stream_ui=False, json_logs=True)
        
        # Verify 
        self.assertEqual(runner.orchestrator.state.round_num, 1)
        # 3 calls: Shark 0 (bad + retry good), Shark 1 (good)
        self.assertEqual(mock_client_inst.session.chat.call_count, 3)
        self.assertIn("agent_0", runner.orchestrator.state.agents)

class TestDashboardFormatting(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock State
        self.state = MarketState(
            round_num=1,
            liquidity_b=100.0,
            whale_wealth=1000.0,
            prompt="Test Prompt"
        )
        self.state.assets = {
            "cand_0": MarketAsset(id="cand_0", type="CANDIDATE", description="Test Candidate"),
            "v_123": MarketAsset(id="v_123", type="VERIFIER", description="Test Verifier")
        }
        self.state.agents = {
            "agent_0": AgentPortfolio(agent_id="agent_0", wealth=500.0)
        }
        
        # Initialize Orchestrator with mocked state
        self.orchestrator = Orchestrator("Test", 1, 1000.0, state=self.state)
        await self.orchestrator.initialize()

    async def test_dashboard_content(self):
        """Render the text dashboard to check for key content."""
        output = self.orchestrator.get_pretty_summary()
        
        # Check Header
        self.assertIn("Round 1", output)
        # Note: Whitespace matching might be fragile, so check distinct parts
        self.assertIn("Whale Wealth:", output)
        self.assertIn("1000.00", output)
        
        # Check Assets
        self.assertIn("cand_0", output)
        self.assertIn("v_123", output)
        
        # Check Agents
        self.assertIn("agent_0", output)
        # 1000 is total budget, but agent has 500
        # self.assertIn("1000.00", output) <- Removed this assumption as agent wealth is 500
        self.assertIn("500.00", output)
        
        # Check Formatting (Plain text)
        self.assertIn("--- Round 1 Summary ---", output)
        self.assertIn("Market Prices:", output)

if __name__ == '__main__':
    unittest.main()