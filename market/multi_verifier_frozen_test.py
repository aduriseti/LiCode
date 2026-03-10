import os
import shutil
import tempfile
import unittest
from unittest import mock

from market.core.state import MarketAsset, MarketBond
from market.core.strategy import Strategy
from market.orchestrator import AgentAction, Orchestrator


class TestMultiVerifierAndFrozenState(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orch = Orchestrator("Verifier Test", n_agents=1, budget=1000.0, base_dir=self.test_dir)
        await self.orch.initialize()
        # agent_0 starts with 1000 wealth

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_test_verifier(self, name, content):
        """Helper to create a verifier directory."""
        path = os.path.join(self.test_dir, "worktrees", "cand_0", name)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "run.sh"), "w") as f:
            f.write("#!/bin/bash\nexit 0")
        with open(os.path.join(path, "test.py"), "w") as f:
            f.write(content)
        return path

    def test_robust_verifier_hashing(self):
        """Verifies that unique directory contents produce unique IDs."""
        path1 = self._create_test_verifier("v1", "print('test 1')")
        path2 = self._create_test_verifier("v2", "print('test 2')")  # Different content
        path3 = self._create_test_verifier("v3", "print('test 1')")  # Same content as v1

        vid1 = self.orch._create_verifier_from_path("agent_0", path1)
        vid2 = self.orch._create_verifier_from_path("agent_0", path2)
        vid3 = self.orch._create_verifier_from_path("agent_0", path3)

        self.assertNotEqual(vid1, vid2, "Different contents should have different IDs")
        self.assertEqual(vid1, vid3, "Same contents should have identical IDs")

    async def test_multi_verifier_proposal_one_round(self):
        """Verifies that an agent can propose multiple verifiers and get multiple bonds."""
        # 1. Create two distinct verifiers
        v1_path = self._create_test_verifier("v1", "content 1")
        v2_path = self._create_test_verifier("v2", "content 2")

        # 2. Submit both in one round
        action = AgentAction(
            agent_id="agent_0",
            beliefs={},
            proposals=[{"type": "VERIFIER", "path": "v1"}, {"type": "VERIFIER", "path": "v2"}],
        )

        with mock.patch.object(self.orch, "_run_oracle", new_callable=mock.AsyncMock):
            await self.orch.process_round([action])

        # 3. Verify two assets created
        vids = [aid for aid, a in self.orch.state.assets.items() if a.type == "VERIFIER"]
        self.assertEqual(len(vids), 2, "Should have created two distinct verifier assets")

        # 4. Verify two bonds created
        agent_bonds = [b for b in self.orch.state.bonds if b.agent_id == "agent_0"]
        self.assertEqual(len(agent_bonds), 2, "Should have two distinct bonds for the agent")

        # 5. Verify agent has shares in both
        for vid in vids:
            self.assertGreater(self.orch.state.agents["agent_0"].shares.get(vid, 0), 0)

    async def test_bond_deduplication(self):
        """Verifies that re-proposing an existing verifier doesn't create a second bond."""
        v1_path = self._create_test_verifier("v1", "content 1")

        # Round 1: Propose
        action = AgentAction("agent_0", proposals=[{"type": "VERIFIER", "path": "v1"}])
        with mock.patch.object(self.orch, "_run_oracle", new_callable=mock.AsyncMock):
            await self.orch.process_round([action])

        bond_count_r1 = len(self.orch.state.bonds)
        self.assertEqual(bond_count_r1, 1)

        # Round 2: Propose same verifier again
        with mock.patch.object(self.orch, "_run_oracle", new_callable=mock.AsyncMock):
            await self.orch.process_round([action])

        # The first bond matured at start of R2, so we check if a NEW one was added.
        # Bond count should be 0 (if matured) or 1 (if new created).
        # But we want to ensure NO NEW bond was added for v1.
        self.assertEqual(
            len(self.orch.state.bonds),
            0,
            "Should not have created a redundant bond for an existing asset",
        )

    async def test_frozen_state_wealth_isolation(self):
        """Verifies that trades use wealth from the START of the round, ignoring matured bond income."""
        # 1. Setup a bond that will mature
        agent = self.orch.state.agents["agent_0"]
        vid = "v_old"
        self.orch.state.assets[vid] = MarketAsset(
            id=vid, type="VERIFIER", description="Old", q_yes=100
        )
        # Bond worth ~73
        self.orch.state.bonds.append(
            MarketBond("agent_0", vid, 100.0, unlock_round=self.orch.state.round_num + 1)
        )

        initial_wealth = agent.wealth  # 1000

        # 2. Round execution
        # In this round, the bond matures (adding ~73 to wealth).
        # We want to verify that the Kelly Strategy used 1000 (frozen) as the budget, not 1073.

        # Agent wants to spend 100% of wealth
        action = AgentAction("agent_0", beliefs={"cand_0": 0.99})

        # We'll spy on Strategy.beliefs_to_wagers to see what wealth it received
        with mock.patch(
            "market.core.strategy.Strategy.beliefs_to_wagers", wraps=Strategy.beliefs_to_wagers
        ) as spy_kelly:
            with mock.patch.object(self.orch, "_run_oracle", new_callable=mock.AsyncMock):
                await self.orch.process_round([action])

            # Check the wealth passed to Kelly
            args, kwargs = spy_kelly.call_args
            passed_wealth = args[1]
            self.assertEqual(
                passed_wealth, initial_wealth, "Kelly should use frozen wealth from round start"
            )
            self.assertNotEqual(
                passed_wealth, agent.wealth, "Kelly should not see the matured bond wealth yet"
            )


if __name__ == "__main__":
    unittest.main()
