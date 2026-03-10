import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from market.core.docker import get_image_name, start_container, stop_container

def test_get_image_name():
    # Should format correctly for x86_64
    assert get_image_name("astropy__astropy-13033") == "ghcr.io/epoch-research/swe-bench.eval.x86_64.astropy__astropy-13033:latest"
    assert get_image_name("django__django-11133") == "ghcr.io/epoch-research/swe-bench.eval.x86_64.django__django-11133:latest"

@pytest.mark.asyncio
@patch('market.core.docker.asyncio.create_subprocess_exec')
async def test_start_container(mock_exec):
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"container_id_123\n", b""))
    mock_proc.returncode = 0
    mock_exec.return_value = mock_proc
    
    container_id = await start_container("my_image", "/host/path")
    
    assert container_id == "container_id_123"
    mock_exec.assert_called_once()
    
    # Check that volume mounts are present
    args = mock_exec.call_args[0]
    assert "-v" in args
    assert "/host/path:/testbed" in args

@pytest.mark.asyncio
@patch('market.core.docker.asyncio.create_subprocess_exec')
async def test_stop_container(mock_exec):
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.returncode = 0
    mock_exec.return_value = mock_proc
    
    await stop_container("container_id_123")
    
    mock_exec.assert_called_once()
    args = mock_exec.call_args[0]
    assert "rm" in args
    assert "-f" in args
    assert "container_id_123" in args
