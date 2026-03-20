import os
import subprocess
import json
import pytest

@pytest.mark.timeout(600)  # Give it up to 10 minutes to pull docker images and run
def test_swe_bench_elo_dummy_pipeline_e2e(tmp_path):
    """
    End-to-end integration test that verifies the full SWE-bench pipeline works for ELO.
    This runs the evaluate_swe_bench_elo.py script in dummy mode.
    It verifies that the script can generate a prediction file.
    """
    prediction_file = tmp_path / "elo_swe_bench_results" / "e2e_test_run" / "predictions.jsonl"
    
    cmd = [
        "python", "evaluate_swe_bench_elo.py",
        "--repo", "pallets/flask",
        "--limit", "1",
        "--dummy",
        "--run-id", "e2e_test_run",
        "--output", str(prediction_file)
    ]
    
    print(f"Running full pipeline: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # 1. Assert script return code (should be 0)
    assert result.returncode == 0, f"evaluate_swe_bench_elo.py failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    
    # 2. Verify the folder structure and prediction file
    assert prediction_file.exists(), "Prediction file was not created."
    
    with open(prediction_file, "r") as f:
        data = json.loads(f.readline().strip())
        assert data["model_patch"] == ""  # Dummy mode returns empty patch
        assert data["model_name_or_path"] == "licode-tournament"
        assert "pallets__flask" in data["instance_id"]
