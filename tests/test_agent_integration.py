import unittest
import asyncio
from licode.agent import LLMAgent, MockOpenCodeSession, Move

class TestLLMAgent(unittest.TestCase):
    def test_prompt_construction_and_parsing(self):
        # 1. Setup Mock Session
        expected_response = {
            "proposed_verifier": "assert 1==1",
            "updated_code": "print('hello')",
            "beliefs": {"s_1": 0.9}
        }
        mock_session = MockOpenCodeSession(expected_response)
        
        # 2. Setup Agent
        agent = LLMAgent("agent_test", mock_session)
        
        # 3. Create Dummy Snapshot
        snapshot = {
            "wealth": {"agent_test": 150.0},
            "sentences": {"s_1": 0.5, "s_2": 0.1}
        }
        
        # 4. Execute
        move = asyncio.run(agent.get_next_move(snapshot))
        
        # 5. Verify Prompt Content
        self.assertIn("MARKET UPDATE", mock_session.last_prompt)
        self.assertIn("Your Wealth: $150.00", mock_session.last_prompt)
        self.assertIn("- s_1: $0.50", mock_session.last_prompt)
        
        # 6. Verify Move Parsing
        self.assertEqual(move.proposed_verifier_content, "assert 1==1")
        self.assertEqual(move.updated_code_content, "print('hello')")
        self.assertEqual(move.belief_vector["s_1"], 0.9)

    def test_invalid_json_handling(self):
        # Setup session that returns garbage
        class BrokenSession:
            async def send_prompt(self, p): return "Not JSON", 0.01
            
        agent = LLMAgent("broken", BrokenSession())
        
        move = asyncio.run(agent.get_next_move({}))
        
        # Should return empty Move (Fold)
        self.assertIsNone(move.proposed_verifier_content)
        self.assertEqual(move.belief_vector, {})

if __name__ == '__main__':
    unittest.main()
