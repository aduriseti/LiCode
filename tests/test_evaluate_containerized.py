import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
from evaluate_swe_bench import run_market_tournament

@pytest.mark.asyncio
@patch('evaluate_swe_bench.status_mgr')
@patch('evaluate_swe_bench.MarketState')
@patch('evaluate_swe_bench.Orchestrator')
@patch('evaluate_swe_bench.asyncio.create_subprocess_exec')
async def test_run_market_tournament_container_lifecycle(mock_exec, mock_orch, mock_state_cls, mock_status_mgr):
    # Setup mocks
    mock_proc = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)
    # Return a final_result JSON to satisfy the state reconstruction logic
    final_result = json.dumps({"type": "final_result", "state": {"some": "state"}})
    mock_proc.stdout.readline = AsyncMock(side_effect=[
        f'{final_result}\n'.encode(),
        b''
    ])
    mock_proc.returncode = 0
    mock_exec.return_value = mock_proc

    mock_state = MagicMock()
    mock_state_cls.from_json.return_value = mock_state

    class Args:
        output = "test_results/predictions.jsonl"
        agents = 2
        rounds = 2
        provider = "test"
        model = "test"
        dashboard = False
        skip_validation = True
        max_retries = 1
        initial_backoff = 10.0
        max_backoff = 100.0

    # Run the function
    # def run_market_tournament(instance_id, work_dir, container_id, args):
    result = await run_market_tournament("test__test-1", "/tmp/workdir", "test_container_id", Args())

    # Verify status updates
    mock_status_mgr.update_status.assert_any_call("test__test-1", "Setting Up Market")
    
    # Verify the market command was wrapped in docker exec
    args, kwargs = mock_exec.call_args
    market_call = args
    assert "docker" in market_call
    assert "exec" in market_call
    assert "test_container_id" in market_call
    assert "market.cli" in market_call
    assert "--agents" in market_call
    assert "2" in market_call
    assert "--rounds" in market_call
    assert "2" in market_call

    # Verify Orchestrator reconstruction
    mock_state_cls.from_json.assert_called_once()
    mock_orch.assert_called_once_with(prompt="", n_agents=0, budget=0, state=mock_state)
    assert result == mock_orch.return_value
