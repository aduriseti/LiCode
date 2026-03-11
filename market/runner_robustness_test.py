import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
import os
import json
from market.runner import MarketRunner
from market.orchestrator import AgentAction
from market.core.state import AgentPortfolio

class MarketRunnerRobustnessTest(unittest.IsolatedAsyncioTestCase):
    """
    Tests for MarketRunner robustness: initialization retries and resilient round execution.
    """

    @patch('market.runner.Shark')
    async def test_setup_agent_retries_on_server_failure(self, MockShark):
        # 1. Setup Runner
        runner = MarketRunner("Test", n_agents=1, budget=100.0)
        runner.orchestrator.initialize = AsyncMock()
        
        # 2. Mock _start_agent_server to fail twice, then succeed
        # This tests the retry loop in _setup_agent
        mock_proc = MagicMock()
        mock_proc.returncode = None
        
        with patch.object(runner, '_start_agent_server') as mock_start:
            mock_start.side_effect = [
                RuntimeError("Start failure 1"),
                RuntimeError("Start failure 2"),
                mock_proc # Success
            ]
            
            # 3. Mock Shark
            shark_inst = MockShark.return_value
            shark_inst.initialize_session = AsyncMock()
            shark_inst.session.id = "ses_123"
            shark_inst.log_path = "/tmp/agent_0.log"
            
            runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)
            
            # 4. Mock os.path.exists for candidate dir
            with patch('market.runner.os.path.exists', return_value=True):
                 await runner.initialize()
            
            self.assertIn("agent_0", runner.sharks)
            # _start_agent_server was called 3 times (2 fails + 1 success)
            self.assertEqual(mock_start.call_count, 3)

    @patch('market.runner.Shark')
    async def test_setup_agent_fails_after_all_retries(self, MockShark):
        runner = MarketRunner("Test", n_agents=1, budget=100.0)
        runner.orchestrator.initialize = AsyncMock()
        
        with patch.object(runner, '_start_agent_server') as mock_start:
            mock_start.side_effect = RuntimeError("Server failed to start")
            
            runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=100.0)
            
            # EXPECTATION: initialize() should NOT crash if an agent fails setup.
            # It should log the error and proceed (sharks will be empty).
            await runner.initialize()
            
            self.assertEqual(len(runner.sharks), 0)
            # Verify it retried 3 times
            self.assertEqual(mock_start.call_count, 3)

    @patch('market.runner.Shark')
    async def test_run_loop_resilient_to_agent_exceptions(self, MockShark):
        runner = MarketRunner("Test", n_agents=2, budget=100.0)
        
        # 1. Setup two sharks
        shark0 = MockShark()
        shark0.get_action = AsyncMock(return_value=AgentAction("agent_0", beliefs={"cand_0": 0.9}))
        shark0.shutdown = AsyncMock()
        
        shark1 = MockShark()
        # Mock a crash that isn't caught by Shark's internal fallback (e.g. unexpected bug)
        shark1.get_action = AsyncMock(side_effect=Exception("Unexpected bug in runner logic"))
        shark1.shutdown = AsyncMock()
        
        runner.sharks = {"agent_0": shark0, "agent_1": shark1}
        
        # 2. Setup orchestrator state
        runner.orchestrator.state.agents["agent_0"] = AgentPortfolio(agent_id="agent_0", wealth=50.0)
        runner.orchestrator.state.agents["agent_1"] = AgentPortfolio(agent_id="agent_1", wealth=50.0)
        runner.orchestrator.process_round = AsyncMock()
        
        # 3. Run loop
        # EXPECTATION: It should NOT crash. Round should proceed with agent_0's action 
        # and a fallback for agent_1.
        await runner.run_loop(max_rounds=1, stream_ui=False)
        
        # Verify process_round was called with actions
        self.assertTrue(runner.orchestrator.process_round.called)
        actions = runner.orchestrator.process_round.call_args[0][0]
        self.assertEqual(len(actions), 2)
        
        # Verify one is the successful action, one is a fallback
        agent_ids = [a.agent_id for a in actions]
        self.assertIn("agent_0", agent_ids)
        self.assertIn("agent_1", agent_ids)
        
        action_1 = next(a for a in actions if a.agent_id == "agent_1")
        self.assertEqual(action_1.beliefs, {})

if __name__ == "__main__":
    unittest.main()
