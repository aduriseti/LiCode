import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from evaluate_swe_bench import run_market_on_instance

@pytest.mark.asyncio
@patch('evaluate_swe_bench.docker')
@patch('evaluate_swe_bench.asyncio.create_subprocess_exec')
@patch('evaluate_swe_bench.asyncio.create_subprocess_shell')
async def test_run_market_on_instance_container_lifecycle(mock_shell, mock_exec, mock_docker):
    # Setup mocks
    mock_docker.get_image_name.return_value = "test_image"
    mock_docker.start_container = AsyncMock(return_value="test_container_id")
    mock_docker.stop_container = AsyncMock()
    mock_docker.pull_image = AsyncMock()
    
    mock_proc = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.communicate = AsyncMock(return_value=(b"{}", b""))
    mock_proc.stdout.readline = AsyncMock(side_effect=[b'{"type": "log", "message": "done"}\n', b''])
    mock_proc.returncode = 0
    
    mock_exec.return_value = mock_proc
    mock_shell.return_value = mock_proc
    
    instance = {
        'instance_id': 'test__test-1',
        'repo': 'test/repo',
        'base_commit': 'abcdef',
        'problem_statement': 'Fix it'
    }
    
    class Args:
        output = "test_output.jsonl"
        agents = 2
        rounds = 2
        run_id = "run_123"
        dummy = False
        max_retries = 1
        initial_backoff = 1
        max_backoff = 1
        provider = "test"
        model = "test"
        dashboard = False
        
    semaphore = asyncio.Semaphore(1)
    
    # Run the function
    await run_market_on_instance(instance, Args(), semaphore)
    
    # Verify Docker lifecycle
    mock_docker.get_image_name.assert_called_with('test__test-1')
    mock_docker.pull_image.assert_called_with("test_image")
    mock_docker.start_container.assert_called_once()
    mock_docker.stop_container.assert_called_with("test_container_id")
    
    # Verify the market command was wrapped in docker exec
    # It might not be the absolute last call if other commands run, but it should be among them
    market_call = [call[0] for call in mock_exec.call_args_list if "market.cli" in call[0]][0]
    assert "docker" in market_call
    assert "exec" in market_call
    assert "test_container_id" in market_call
    assert any("python3" in arg for arg in market_call)
    assert "-m" in market_call
    assert "market.cli" in market_call
