import pytest
import asyncio
import os
import shutil
import json
from unittest.mock import MagicMock

from market.common.agent import AgentSession, AgentState

@pytest.fixture
def base_dir(tmp_path):
    d = tmp_path / "agent_test_dir"
    d.mkdir()
    return str(d)

@pytest.mark.asyncio
async def test_agent_basic_interaction(base_dir):
    """
    Spawns a real opencode serve instance for a test agent,
    sends a simple prompt, verifies the response, and checks the traces.
    """
    agent_id = "test_agent_99"
    traces_dir = os.path.join(base_dir, "traces")
    os.makedirs(traces_dir, exist_ok=True)
    
    # Use AgentSession because it has start() which boots the server
    # We pass a dummy orchestrator
    mock_orchestrator = MagicMock()
    
    session = AgentSession(
        agent_id=agent_id,
        worktree_dir=base_dir,
        agent_type="candidate",
        model="gemini-3-flash",
        provider="opencode",
        traces_dir=traces_dir,
        orchestrator=mock_orchestrator
    )
    
    # We don't want the full infinite loop to trap us, so we just boot the server directly
    # and then call chat_robust manually.
    from market.common.server import start_opencode_server, find_free_port
    session.port = find_free_port()
    
    from opencode_ai import AsyncOpencode
    session.client = AsyncOpencode(base_url=f"http://127.0.0.1:{session.port}", timeout=30.0, max_retries=0)
    
    session.process = await start_opencode_server(
        agent_id=session.agent_id,
        agent_dir=session.worktree_dir,
        port=session.port,
        model=session.model,
        provider=session.provider,
        traces_dir=traces_dir
    )
    
    try:
        # Prompt it to return exactly the JSON we want
        test_prompt = "Return exactly this JSON: {\"action\": \"update_candidate\", \"message\": \"test works\"}"
        system_prompt = "You are a helpful assistant."
        
        response = await session.chat_robust(test_prompt, system_prompt)
        
        assert "update_candidate" in response
        
        # Verify trace file was created and contains the prompt/response
        trace_file = os.path.join(traces_dir, f"{agent_id}_stream.txt")
        assert os.path.exists(trace_file)
        
        with open(trace_file, "r") as f:
            content = f.read()
            assert "[PROMPT]" in content
            assert test_prompt in content
            assert "[ASSISTANT]" in content
            assert "update_candidate" in content
            
        assert session.state == AgentState.THINKING
            
    finally:
        await session.shutdown()
        assert session.state == AgentState.TERMINATED
