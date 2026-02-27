import unittest
from unittest import mock
import os
import shutil
import stat
import tempfile
from market.orchestrator import Orchestrator, AgentAction
from market.core.state import MarketState, AgentPortfolio, MarketAsset, MarketBond

class TestOrchestrator(unittest.IsolatedAsyncioTestCase):
    
    async def test_basic_loop(self):
        # Init
        orch = Orchestrator("Solve X", n_agents=2, budget=1000.0)
        await orch.initialize()
        
        self.assertEqual(len(orch.state.agents), 2)
        self.assertEqual(len(orch.state.assets), 2) # 2 candidates
        
        # Initial prices should be 0.5 (1/N for N=2)
        p0 = orch.state.get_asset_price("cand_0")
        self.assertAlmostEqual(p0, 0.5)
        
        # Round 1: Agent 0 bets on themselves
        # Belief must be > p0 (0.5) to move price up.
        action_0 = AgentAction(
            agent_id="agent_0",
            beliefs={"cand_0": 0.7} 
        )
        
        await orch.process_round([action_0])
        
        # Verify Price Move
        p1 = orch.state.get_asset_price("cand_0")
        self.assertTrue(p1 > 0.5)
        
        # Verify Wealth Change
        if "agent_0" in orch.state.agents:
            # Agent 0 started with 500.
            # They were the ONLY ones to trade, so payout == cost (zero profit).
            # Wealth should be 500 - inference_tax.
            w1 = orch.state.agents["agent_0"].wealth
            tax = orch.inference_tax
            self.assertAlmostEqual(w1, 500.0 - tax, places=4)
            # In Instant Settlement, shares are transferred to Whale at round end
            shares = orch.state.agents["agent_0"].shares.get("cand_0", 0.0)
            self.assertEqual(shares, 0)
        else:
            self.fail("Agent 0 went bankrupt too fast")

    async def test_payout_on_price_move(self):
        """Verify that agents realize profit when price moves further in their direction."""
        orch = Orchestrator("Profit Test", n_agents=2, budget=1000.0)
        await orch.initialize()
        
        # 1. Agent 0 bets cand_0 is 60% (from 50%)
        action_0 = AgentAction("agent_0", beliefs={"cand_0": 0.6})
        
        # 2. We mock the Whale to move the price to 90% AFTER the agent bets
        # In process_round, Whale.generate_trades is called after Agent trades.
        whale_move = [("cand_0", 100.0)] # High YES bet
        
        with mock.patch('market.orchestrator.Whale.generate_trades', return_value=whale_move):
            # Mock oracle to do nothing
            with mock.patch.object(orch, '_run_oracle', new_callable=mock.AsyncMock):
                await orch.process_round([action_0])
            
        # 3. Verify
        # Agent settled at the final price (moved up by Whale).
        agent = orch.state.agents["agent_0"]
        # Wealth > 500 - tax (Profit > 0)
        self.assertTrue(agent.wealth > (500.0 - orch.inference_tax))

    async def test_whale_intervention(self):
        orch = Orchestrator("Solve X", n_agents=2)
        await orch.initialize()
        
        # Add a verifier manually
        from market.core.state import MarketAsset
        orch.state.assets["v1"] = MarketAsset(id="v1", type="VERIFIER", description="Manual V", q_yes=100) # Price > 0.5
        
        # Set failure
        orch.state.test_failures["v1:cand_0"] = True
        
        # Round 1
        await orch.process_round([])
        
        # Whale should have shorted cand_0
        p_cand0 = orch.state.get_asset_price("cand_0")
        self.assertTrue(p_cand0 < 0.5)

    async def test_pretty_summary(self):
        orch = Orchestrator("Display Test", n_agents=2)
        await orch.initialize()
        summary = orch.get_pretty_summary()
        
        # Verify basic structure
        self.assertIn("Round 0 Summary", summary)
        self.assertIn("Prices", summary)
        self.assertIn("cand_0", summary)
        self.assertIn("Whale Wealth", summary)
        
        # Verify it runs on a later round too
        orch.state.round_num = 10
        summary_10 = orch.get_pretty_summary()
        self.assertIn("Round 10 Summary", summary_10)

    async def test_symmetric_wealth_conservation(self):
        """Verify that Whale wealth is perfectly conserved during its own trades."""
        orch = Orchestrator("Test", n_agents=1, budget=1000.0)
        await orch.initialize()
        
        initial_whale_wealth = orch.state.whale_wealth
        
        # Simulate a Whale active trade (deductive)
        # Whale wants to buy 50 YES shares of cand_0
        trades = [("cand_0", 50.0)]
        orch._execute_trades("whale", trades)
        
        # Whale wealth should be EXACTLY the same (-cost + cost)
        self.assertEqual(orch.state.whale_wealth, initial_whale_wealth)
        # But price should have moved
        self.assertTrue(orch.state.get_asset_price("cand_0") > 0.5)

    async def test_agent_to_whale_transfer(self):
        """Verify that agent payments are correctly transferred to the Whale."""
        orch = Orchestrator("Test", n_agents=1, budget=1000.0)
        await orch.initialize()
        
        initial_whale_wealth = orch.state.whale_wealth
        initial_agent_wealth = orch.state.agents["agent_0"].wealth
        
        # Agent 0 buys 50 shares
        trades = [("cand_0", 50.0)]
        orch._execute_trades("agent_0", trades)
        
        agent_wealth_after = orch.state.agents["agent_0"].wealth
        whale_wealth_after = orch.state.whale_wealth
        
        cost = initial_agent_wealth - agent_wealth_after
        self.assertTrue(cost > 0)
        self.assertAlmostEqual(whale_wealth_after, initial_whale_wealth + cost, places=5)

class TestBondLogic(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state = MarketState(
            round_num=0,
            liquidity_b=100.0,
            whale_wealth=2000.0,
            prompt="test"
        )
        # Use agent_0 to match Orchestrator(n=1) defaults
        self.orch = Orchestrator("test", 1, state=self.state, base_dir=self.test_dir)
        await self.orch.initialize()
        # Orchestrator init creates agent_0 and cand_0. 
        # Override wealth for test
        self.state.agents["agent_0"].wealth = 1000.0

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    def test_bond_lifecycle(self):
        # 1. Create Verifier Files in Worktree
        cand_dir = os.path.join(self.test_dir, "worktrees", "cand_0")
        v_src = os.path.join(cand_dir, "tests", "v1")
        os.makedirs(v_src, exist_ok=True)
        with open(os.path.join(v_src, "run.sh"), "w") as f:
            f.write("#!/bin/bash\necho hello")
            
        proposal = {
            "type": "VERIFIER",
            "path": "tests/v1"
        }
        
        # This will create a bond via Strategy logic
        full_src = os.path.join(cand_dir, "tests", "v1")
        vid = self.orch._create_verifier_from_path("agent_0", full_src)
        
        self.assertIsNotNone(vid)
        
        # Check Bond exists
        self.assertEqual(len(self.state.bonds), 1)
        bond = self.state.bonds[0]
        self.assertEqual(bond.agent_id, "agent_0")
        self.assertEqual(bond.asset_id, vid)
        self.assertTrue(bond.q_shares > 0)
        
        # Check Agent Shares
        shares = self.state.agents["agent_0"].shares.get(vid, 0.0)
        self.assertAlmostEqual(shares, bond.q_shares)
        
        # Check Cost (Wealth should decrease)
        self.assertTrue(self.state.agents["agent_0"].wealth < 1000.0)
        
        # 2. Advance Round (Matures immediately if lock=1 and next round is 1)
        self.state.round_num += 1
        self.orch._mature_bonds()
        
        # Should be matured now (unlock=1, round=1)
        self.assertEqual(len(self.state.bonds), 0)
        
        # 3. Verify Payout
        shares_after = self.state.agents["agent_0"].shares.get(vid, 0.0)
        self.assertAlmostEqual(shares_after, 0.0)
        
        final_wealth = self.state.agents["agent_0"].wealth
        # LMSR is path independent. Buying X then Selling X returns to original state if b is constant.
        self.assertAlmostEqual(final_wealth, 1000.0, places=4)

    async def test_instant_settlement(self):
        """Verify that belief-based trades are resolved but bonds stay locked."""
        orch = Orchestrator("Test", n_agents=1, budget=1000.0)
        await orch.initialize()
        
        # 1. Setup a Verifier source in the worktree
        cand_dir = os.path.join(orch.base_dir, "worktrees", "cand_0")
        v_src = os.path.join(cand_dir, "v1")
        os.makedirs(v_src, exist_ok=True)
        with open(os.path.join(v_src, "run.sh"), "w") as f: f.write("#!/bin/bash\nexit 0")
        
        # 2. Create an action that both proposes the verifier AND places a bet
        action = AgentAction("agent_0", 
            beliefs={"cand_0": 0.6},
            proposals=[{"type": "VERIFIER", "path": "v1"}]
        )
        
        # 3. Process Round
        # Mock oracle to avoid FS overhead
        with mock.patch.object(orch, '_run_oracle', new_callable=mock.AsyncMock):
            await orch.process_round([action])
            
        # 4. Verify
        # Agent should have NO shares of cand_0 (settled)
        # Agent should STILL HAVE shares of the new verifier (locked bond)
        agent = orch.state.agents["agent_0"]
        self.assertEqual(agent.shares.get("cand_0", 0.0), 0.0)
        
        # Find the verifier ID (it's v_HASH)
        vids = [aid for aid, a in orch.state.assets.items() if a.type == "VERIFIER"]
        self.assertEqual(len(vids), 1)
        vid = vids[0]
        
        self.assertTrue(agent.shares.get(vid, 0.0) > 0)
        
        # Verify Whale deductive positions also settled
        self.assertEqual(len(orch.state.whale_shares), 0)

class TestOrchestratorVerifier(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orchestrator = Orchestrator(
            prompt="test prompt",
            n_agents=1,
            base_dir=self.test_dir
        )
        await self.orchestrator.initialize()
        # agent_0 created by initialize

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    def test_create_verifier_from_path(self):
        """Test creating a verifier from an existing directory."""
        # Create source in cand_0
        cand_dir = os.path.join(self.test_dir, "worktrees", "cand_0")
        src_dir = os.path.join(cand_dir, "my_test")
        os.makedirs(src_dir, exist_ok=True)
        
        with open(os.path.join(src_dir, "run.sh"), "w") as f:
            f.write("#!/bin/bash\nexit 0")
        with open(os.path.join(src_dir, "data.txt"), "w") as f:
            f.write("some data")
            
        vid = self.orchestrator._create_verifier_from_path("agent_0", src_dir)
        self.assertIsNotNone(vid)
        
        # Verify it was copied to verifiers dir
        v_path = os.path.join(self.orchestrator.verifiers_dir, vid)
        self.assertTrue(os.path.exists(os.path.join(v_path, "run.sh")))
        self.assertTrue(os.path.exists(os.path.join(v_path, "data.txt")))
        
        # Check permissions
        st = os.stat(os.path.join(v_path, "run.sh"))
        self.assertTrue(st.st_mode & stat.S_IXUSR)

    def test_create_verifier_missing_run_sh(self):
        """Test failure when run.sh is missing."""
        cand_dir = os.path.join(self.test_dir, "worktrees", "cand_0")
        src_dir = os.path.join(cand_dir, "bad_test")
        os.makedirs(src_dir, exist_ok=True)
        with open(os.path.join(src_dir, "test.py"), "w") as f:
            f.write("print('hi')")
            
        vid = self.orchestrator._create_verifier_from_path("agent_0", src_dir)
        self.assertIsNone(vid)

class PermissionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orch = Orchestrator("Test Perms", n_agents=1, base_dir=self.test_dir)
        await self.orch.initialize()

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    def test_candidate_dir_permissions(self):
        # Check cand_0 directory
        cand_dir = os.path.join(self.test_dir, "worktrees", "cand_0")
        self.assertTrue(os.path.exists(cand_dir))
        
        mode = os.stat(cand_dir).st_mode
        # Check for 700 (rwx------) - changed from 755 for isolation
        self.assertEqual(mode & 0o777, 0o700)

    async def test_verifier_dir_permissions(self):
        # Create verifier source
        cand_dir = os.path.join(self.test_dir, "worktrees", "cand_0")
        src_dir = os.path.join(cand_dir, "v1")
        os.makedirs(src_dir, exist_ok=True)
        with open(os.path.join(src_dir, "run.sh"), "w") as f:
            f.write("echo ok")
        
        # Create proposal
        action = AgentAction("agent_0", proposals=[
            {"type": "VERIFIER", "path": "v1"}
        ])
        await self.orch.process_round([action])
        
        # Find the verifier dir
        v_base = os.path.join(self.test_dir, "verifiers")
        v_dirs = os.listdir(v_base)
        self.assertTrue(len(v_dirs) > 0)
        
        v_path = os.path.join(v_base, v_dirs[0])
        mode = os.stat(v_path).st_mode
        self.assertEqual(mode & 0o777, 0o755)
        
        # Check run.sh (755)
        run_sh = os.path.join(v_path, "run.sh")
        mode_sh = os.stat(run_sh).st_mode
        self.assertEqual(mode_sh & 0o777, 0o755)

if __name__ == '__main__':
    unittest.main()
