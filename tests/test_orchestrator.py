import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import shutil
import os
import asyncio
from licode.orchestrator import Orchestrator
from licode.agent import Move

class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator("Test Prompt", agent_count=2, budget=100.0)

    def tearDown(self):
        if os.path.exists(self.orchestrator.temp_dir):
            shutil.rmtree(self.orchestrator.temp_dir)

    def test_initialization(self):
        self.assertEqual(len(self.orchestrator.agents), 2)
        self.assertTrue(os.path.exists(self.orchestrator.worktrees_dir))
        self.assertTrue(os.path.exists(self.orchestrator.verifiers_dir))
        # Check initial goal sentences
        self.assertEqual(len(self.orchestrator.goal_sentences), 2)

    @patch("licode.verifier.Verifier.execute")
    def test_tick_processing(self, mock_execute):
        # Mock verifier execution to avoid subprocess
        mock_execute.return_value = True # Default pass
        
        # Mock Agent Moves using AsyncMock since get_next_move is async
        # We need to patch the agents in self.orchestrator.agents
        
        move1 = Move(
            proposed_verifier_content="assert True", 
            belief_vector={list(self.orchestrator.goal_sentences.values())[0]: 0.9}
        )
        move2 = Move(
            updated_code_content="def solve(): return 1",
            belief_vector={list(self.orchestrator.goal_sentences.values())[1]: 0.8}
        )
        
        self.orchestrator.agents[0].get_next_move = AsyncMock(return_value=move1)
        self.orchestrator.agents[1].get_next_move = AsyncMock(return_value=move2)
        
        # Run one tick
        asyncio.run(self.orchestrator.tick())
        
        # Check if verifier file was created
        self.assertTrue(len(os.listdir(self.orchestrator.verifiers_dir)) > 0)
        
        # Check if code was updated
        wt_path = os.path.join(self.orchestrator.worktrees_dir, "minnow_1", "main.py")
        with open(wt_path, "r") as f:
            content = f.read()
        self.assertIn("return 1", content)
        
        # Check if beliefs were submitted
        s_id_0 = list(self.orchestrator.goal_sentences.values())[0]
        self.assertEqual(self.orchestrator.market.sentences[s_id_0].beliefs["minnow_0"], 0.9)

    @patch("licode.verifier.Verifier.execute")
    def test_whale_trigger_integration(self, mock_execute):
        # Scenario: 
        # Agent 0 proposes a test.
        # Agent 0 PASSES the test.
        # Agent 1 FAILS the test.
        # Whale should short Agent 1.
        
        # Setup specific return values for verifier.execute
        # It is called for each candidate.
        # Let's say we have 1 active verifier.
        # It calls execute(wt_0) then execute(wt_1)
        
        # We need to manually inject a verifier sentence to ensure the loop picks it up
        v_path = os.path.join(self.orchestrator.verifiers_dir, "trigger_test.py")
        with open(v_path, "w") as f: f.write("pass")
        s_id_ver = self.orchestrator.market.register_sentence("Trigger Test", verifier_path=v_path)
        
        def side_effect(path):
            if "minnow_0" in path: return True # Witness
            if "minnow_1" in path: return False # Victim
            return None
            
        mock_execute.side_effect = side_effect
        
        # Mock agents to do nothing to avoid noise
        for a in self.orchestrator.agents:
            a.get_next_move = AsyncMock(return_value=Move())
            
        asyncio.run(self.orchestrator.tick())
        
        # Check Whale belief on Agent 1's goal
        goal_s_id_1 = self.orchestrator.goal_sentences["minnow_1"]
        whale_belief = self.orchestrator.market.sentences[goal_s_id_1].beliefs.get("whale")
        
        self.assertAlmostEqual(whale_belief, 0.0, delta=1e-5)
        
        # Also check if Goal was Settled as False
        self.assertFalse(self.orchestrator.market.sentences[goal_s_id_1].resolved_value)

if __name__ == '__main__':
    unittest.main()
