import pytest
import asyncio
import os
import shutil
import tempfile
from market.common.oracle import CommonOracle, ResultType

@pytest.fixture
def temp_candidate_dir():
    d = tempfile.mkdtemp()
    # Create a dummy README.md
    with open(os.path.join(d, "README.md"), "w") as f:
        f.write("test candidate")
    # Initialize git repo to allow git apply
    import subprocess
    subprocess.run(["git", "init"], cwd=d, check=True)
    subprocess.run(["git", "add", "."], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=d, check=True)
    
    yield d
    shutil.rmtree(d)

@pytest.mark.asyncio
async def test_run_test_success(temp_candidate_dir):
    res, stdout, stderr = await CommonOracle.run_test(
        candidate_dir=temp_candidate_dir,
        entrypoint="echo 'Hello World'"
    )
    assert res == ResultType.PASS
    assert "Hello World" in stdout

@pytest.mark.asyncio
async def test_run_test_failure(temp_candidate_dir):
    res, stdout, stderr = await CommonOracle.run_test(
        candidate_dir=temp_candidate_dir,
        entrypoint="echo 'Error occurred' >&2; exit 1"
    )
    assert res == ResultType.FAIL
    assert "Error occurred" in stderr

@pytest.mark.asyncio
async def test_run_test_patch_error(temp_candidate_dir):
    # Create an invalid patch
    invalid_patch = "invalid patch content"
    res, stdout, stderr = await CommonOracle.run_test(
        candidate_dir=temp_candidate_dir,
        patch_content=invalid_patch,
        entrypoint="exit 0"
    )
    assert res == ResultType.PATCH_ERROR
    assert "Failed to apply verifier patch" in stderr
