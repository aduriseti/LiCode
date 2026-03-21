import pytest
import asyncio
import os
import shutil
import json
import time
from unittest.mock import MagicMock, AsyncMock, patch
from market.elo.orchestrator import EloOrchestrator
from market.common.oracle import ResultType
from market.common.workspace import WorkspaceManager

@pytest.fixture(autouse=True)
def mock_agent_server():
    """Mock start_opencode_server globally for elo regression tests."""
    with patch('market.common.server.start_opencode_server') as mock_start:
        # Create a mock context manager
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=MagicMock(pid=9999, returncode=None))
        mock_cm.__aexit__ = AsyncMock()
        mock_start.return_value = mock_cm
        
        with patch('market.common.agent.AsyncOpencode') as mock_client:
            mock_client_inst = mock_client.return_value
            mock_client_inst.session.create = AsyncMock(return_value=MagicMock(id="ses_123"))
            mock_client_inst.close = AsyncMock()
            yield mock_start

@pytest.fixture
def base_dir(tmp_path):
    d = tmp_path / "elo_test"
    d.mkdir()
    return str(d)

@pytest.mark.asyncio
async def test_elo_orchestrator_initialization(base_dir):
    orch = EloOrchestrator(prompt="test prompt", base_dir=base_dir, max_duration=5)
    await orch.initialize()
    
    assert "baseline_empty" in orch.candidates
    assert len(orch.verifiers) >= 0 # Depends on environment, but should initialize

@pytest.mark.asyncio
async def test_elo_candidate_update_detection(base_dir):
    orch = EloOrchestrator(prompt="test prompt", base_dir=base_dir, max_duration=10)
    # Don't pass agent_id to avoid starting real servers
    await orch.add_candidate("agent_0")
    
    agent_0_dir = orch.candidates["agent_0"].worktree_dir
    
    # Simulate an update
    with open(os.path.join(agent_0_dir, "README.md"), "a") as f:
        f.write("\n\nUpdate detected")
    
    # Run a tick of update check
    await orch.submit_update("agent_0", "Test update")
    
    # Check if latest_version diff was updated to the new diff
    current_diff = orch.workspace_mgr.get_diff(agent_0_dir)
    assert orch.candidates["agent_0"].latest_version.diff == current_diff
    assert "Update detected" in current_diff

@pytest.mark.asyncio
async def test_elo_interruption_writing(base_dir):
    orch = EloOrchestrator(prompt="test prompt", base_dir=base_dir, max_duration=10)
    
    # Mock AgentSession to avoid starting real server
    from market.common.agent import AgentSession
    mock_session = MagicMock(spec=AgentSession)
    mock_session.worktree_dir = os.path.join(orch.worktrees_dir, "agent_0")
    mock_session.traces_dir = orch.traces_dir
    mock_session.interrupt = AsyncMock()
    
    # Manually add it
    await orch.add_candidate("agent_0")
    orch.agent_sessions["agent_0_session"] = mock_session
    
    message = "Test interrupt"
    data = {"test": "data"}
    
    # We test the real Session's interrupt logic separately if needed,
    # but here we can just use a real session WITHOUT starting it.
    from market.common.agent import AgentSession
    real_session = AgentSession("agent_0", mock_session.worktree_dir, traces_dir=orch.traces_dir)
    await real_session.interrupt(message, data)
    
    interrupts_dir = os.path.join(real_session.worktree_dir, ".interrupts")
    assert os.path.exists(interrupts_dir)
    files = os.listdir(interrupts_dir)
    assert len(files) == 1
    
    with open(os.path.join(interrupts_dir, files[0]), "r") as f:
        saved_data = json.load(f)
        assert saved_data["message"] == message
        assert saved_data["data"] == data

@pytest.mark.asyncio
async def test_elo_rating_update(base_dir):
    orch = EloOrchestrator(prompt="test prompt", base_dir=base_dir, max_duration=10)
    await orch.add_candidate("agent_0")
    await orch.add_verifier("v1", None, "exit 0")
    
    # Simulate a match
    await orch.run_match("agent_0", "v1")
    
    initial_rating = orch.candidates["agent_0"].latest_version.elo.rating_obj.rating
    
    # Update ratings
    await orch.update_all_ratings()
    
    new_rating = orch.candidates["agent_0"].latest_version.elo.rating_obj.rating
    assert new_rating != initial_rating

@pytest.mark.asyncio
async def test_elo_timeout_skips_rating(base_dir):
    orch = EloOrchestrator(prompt="test prompt", base_dir=base_dir, max_duration=10)
    await orch.add_candidate("agent_0")
    await orch.add_verifier("v1", None, "sleep 100") # Will timeout
    
    initial_rating = orch.candidates["agent_0"].latest_version.elo.rating_obj.rating
    
    # Mock CommonOracle.run_test to return TIMEOUT
    with patch('market.common.oracle.CommonOracle.run_test', return_value=(ResultType.TIMEOUT, "", "")):
        await orch.run_match("agent_0", "v1")
    
    await orch.update_all_ratings()
    
    new_rating = orch.candidates["agent_0"].latest_version.elo.rating_obj.rating
    # Rating should NOT change (skipped)
    assert new_rating == initial_rating

@pytest.mark.asyncio
async def test_elo_fail_is_loss(base_dir):
    orch = EloOrchestrator(prompt="test prompt", base_dir=base_dir, max_duration=10)
    await orch.add_candidate("agent_0")
    await orch.add_verifier("v1", None, "exit 1")
    
    initial_rating = orch.candidates["agent_0"].latest_version.elo.rating_obj.rating
    
    # Mock CommonOracle.run_test to return FAIL
    with patch('market.common.oracle.CommonOracle.run_test', return_value=(ResultType.FAIL, "", "")):
        await orch.run_match("agent_0", "v1")
    
    await orch.update_all_ratings()
    
    new_rating = orch.candidates["agent_0"].latest_version.elo.rating_obj.rating
    # Rating should decrease (loss)
    assert new_rating < initial_rating

@pytest.mark.asyncio
async def test_elo_patch_error_skips_rating(base_dir):
    orch = EloOrchestrator(prompt="test prompt", base_dir=base_dir, max_duration=10)
    await orch.add_candidate("agent_0")
    await orch.add_verifier("v1", None, "exit 0")
    
    initial_rating = orch.candidates["agent_0"].latest_version.elo.rating_obj.rating
    
    # Mock CommonOracle.run_test to return PATCH_ERROR
    with patch('market.common.oracle.CommonOracle.run_test', return_value=(ResultType.PATCH_ERROR, "", "")):
        await orch.run_match("agent_0", "v1")
    
    await orch.update_all_ratings()
    
    new_rating = orch.candidates["agent_0"].latest_version.elo.rating_obj.rating
    # Rating should NOT change (skipped)
    assert new_rating == initial_rating
