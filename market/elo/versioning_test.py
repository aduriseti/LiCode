import pytest
import asyncio
import os
import shutil
import json
import time
import logging
from market.elo.orchestrator import EloOrchestrator
from market.common.workspace import WorkspaceManager

# Configure logging
logging.basicConfig(level=logging.INFO)

@pytest.fixture
def base_dir(tmp_path):
    d = tmp_path / "elo_versioning_test"
    d.mkdir()
    return str(d)

@pytest.mark.asyncio
async def test_action_based_version_creation(base_dir):
    """Verifies that versions are ONLY created via submit_update, not polling."""
    orch = EloOrchestrator(prompt="test", base_dir=base_dir)
    await orch.add_candidate("agent_0")
    cand = orch.candidates["agent_0"]
    
    assert len(cand.versions) == 1
    
    # 1. Manually write a file
    with open(os.path.join(cand.worktree_dir, "new_file.py"), "w") as f:
        f.write("print(1)")
    
    # 2. Polling should do NOTHING now
    await orch.check_for_updates()
    assert len(cand.versions) == 1, "Version should not be created by polling"
    
    # 3. Explicit submission should create version
    await orch.submit_update("agent_0", "First Update")
    assert len(cand.versions) == 2
    assert cand.versions[1].index == 1
    assert "print(1)" in cand.versions[1].diff

@pytest.mark.asyncio
async def test_gitignore_pollution_prevention(base_dir):
    """Verifies that node_modules, .interrupts, and other ignored files don't appear in diffs."""
    orch = EloOrchestrator(prompt="test", base_dir=base_dir)
    await orch.add_candidate("agent_0")
    cand = orch.candidates["agent_0"]
    
    # Create a node_modules directory (which is in our new .gitignore)
    nm_dir = os.path.join(cand.worktree_dir, "node_modules")
    os.makedirs(nm_dir, exist_ok=True)
    with open(os.path.join(nm_dir, "secret.txt"), "w") as f:
        f.write("ignore me")
        
    # Create an .interrupts directory
    int_dir = os.path.join(cand.worktree_dir, ".interrupts")
    os.makedirs(int_dir, exist_ok=True)
    with open(os.path.join(int_dir, "interrupt_123.json"), "w") as f:
        f.write('{"message": "test"}')
        
    # Create a real change
    with open(os.path.join(cand.worktree_dir, "real_change.py"), "w") as f:
        f.write("print('hello')")
        
    # Submit update
    await orch.submit_update("agent_0", "Adding real change")
    
    latest_diff = cand.latest_version.diff
    assert "real_change.py" in latest_diff
    assert "node_modules" not in latest_diff, "node_modules polluted the diff despite gitignore"
    assert "ignore me" not in latest_diff
    assert ".interrupts" not in latest_diff, ".interrupts polluted the diff despite gitignore"
    assert "interrupt_123.json" not in latest_diff

@pytest.mark.asyncio
async def test_version_rating_isolation(base_dir):
    """Verifies that matches only impact the pinned version."""
    orch = EloOrchestrator(prompt="test", base_dir=base_dir)
    await orch.add_candidate("agent_0")
    await orch.add_verifier("v1", None, "exit 0")
    
    cand = orch.candidates["agent_0"]
    
    # Initial match for v0
    await orch.run_match("agent_0", "v1", version_idx=0)
    await orch.wait_for_matches()
    await orch.update_all_ratings()
    v0_rating = cand.versions[0].elo.rating_obj.rating
    assert v0_rating > 1500.0
    
    # Create v1
    with open(os.path.join(cand.worktree_dir, "v1.py"), "w") as f:
        f.write("v1")
    await orch.submit_update("agent_0", "Create v1")
    await orch.wait_for_matches()
    assert len(cand.versions) == 2
    
    # Run a match for v1 that FAILS (exit 1)
    await orch.add_verifier("v2", None, "exit 1")
    await orch.run_match("agent_0", "v2", version_idx=1)
    await orch.wait_for_matches()
    await orch.update_all_ratings()
    
    # v1 rating should be lower than its inherited rating
    assert cand.versions[1].elo.rating_obj.rating < v0_rating
    # v0 rating should be UNCHANGED
    assert cand.versions[0].elo.rating_obj.rating == v0_rating

@pytest.mark.asyncio
async def test_episode_reset_rd_behavior(base_dir):
    """Verifies that when a candidate updates code, the new version inherits the rating but resets RD to 350.0."""
    orch = EloOrchestrator(prompt="test", base_dir=base_dir)
    await orch.add_candidate("agent_0")
    
    cand = orch.candidates["agent_0"]
    v0 = cand.versions[0]
    
    # Artificially set v0 rating to something non-default to prove it inherits
    v0.elo.rating_obj.setRating(1600.0)
    v0.elo.rating_obj.setRd(40.0) # Very low uncertainty
    
    # Create an update to trigger a new version
    with open(os.path.join(cand.worktree_dir, "v1.py"), "w") as f:
        f.write("v1")
    await orch.submit_update("agent_0", "Create v1")
    
    # Verify version 1 was created
    assert len(cand.versions) == 2
    v1 = cand.versions[1]
    
    # 1. Rating should be exactly inherited
    assert v1.elo.rating_obj.rating == 1600.0
    
    # 2. RD should be reset to the unrated maximum (350.0)
    assert v1.elo.rating_obj.rd == 350.0
    
    # 3. Old version should remain untouched
    assert v0.elo.rating_obj.rating == 1600.0
    assert v0.elo.rating_obj.rd == 40.0
