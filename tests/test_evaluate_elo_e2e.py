import os
import subprocess
import glob
import time
import json
import sys
import shutil
import pytest

@pytest.mark.timeout(400)
def test_elo_tournament_e2e():
    """
    Runs an end-to-end test of the ELO tournament CLI with 4 agents.
    Verifies per-agent actions via structured JSON logs.
    """
    # Setup test parameters
    max_duration = 180 
    num_agents = 4 # 2 candidates, 2 testers (1:1 ratio)
    
    # Refined Prompt to reduce agent confusion
    prompt = "Implement a function fib(n: int) -> int in a file named solution.py that returns the nth Fibonacci number (fib(0)=0, fib(1)=1). Testing agents: Your tests MUST import fib from solution.py."
    
    cmd = [
        sys.executable, "-m", "market.elo.cli",
        "run",
        "--prompt", prompt,
        "--agents", str(num_agents),
        "--max-duration", str(max_duration),
        "--output-dir", ".arenas",
        "--model", "gemini-3-flash",
        "--provider", "opencode"
    ]
    
    print(f"Running ELO tournament: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    
    assert result.returncode == 0, f"ELO CLI failed with code {result.returncode}"
    
    # Find newest run directory
    elo_runs = sorted(glob.glob(".arenas/elo_run_*"), key=os.path.getmtime, reverse=True)
    assert len(elo_runs) > 0
    latest_run_dir = elo_runs[0]
    
    # 1. Parse Structured JSON Events from log
    log_path = os.path.join(latest_run_dir, "logs", "tournament.log")
    events = []
    with open(log_path, "r") as f:
        for line in f:
            if "EVENT_JSON:" in line:
                try:
                    json_str = line.split("EVENT_JSON:")[1].strip()
                    events.append(json.loads(json_str))
                except Exception:
                    continue
    
    # 2. Strict Per-Agent Assertions
    candidate_ids = ["agent_0", "agent_2"]
    tester_ids = ["agent_1", "agent_3"]
    
    updates_by_cid = {e["data"]["candidate_id"] for e in events if e["type"] == "update_submitted"}
    proposals_by_tid = {e["data"]["id"] for e in events if e["type"] == "tester_added"} # We track session creation
    
    # Actually check for 'verifier_added' events linked to testers
    # verifier_added data: {id: vid, entrypoint: ...}
    # vid format: test_{agent_id}_{timestamp}
    proposals = {e["data"]["id"] for e in events if e["type"] == "verifier_added"}
    proposers = set()
    for vid in proposals:
        if vid.startswith("test_agent_"):
            # Extract agent_id from test_agent_N_timestamp
            parts = vid.split("_")
            agent_id = f"{parts[1]}_{parts[2]}"
            proposers.add(agent_id)

    print(f"Updates from: {updates_by_cid}")
    print(f"Tests from Agents: {proposers}")

    for cid in candidate_ids:
        assert cid in updates_by_cid, f"Candidate {cid} failed to submit an update"
        
    for tid in tester_ids:
        assert tid in proposers, f"Tester {tid} failed to propose a test"

    # 3. Verify Isolated Match Logs
    match_logs_dir = os.path.join(latest_run_dir, "logs", "matches")
    assert os.path.exists(match_logs_dir)
    assert len(os.listdir(match_logs_dir)) > 0
    
    # 4. Verify Leaderboard Deviation
    results_path = os.path.join(latest_run_dir, "elo_results.json")
    with open(results_path, "r") as f:
        results = json.load(f)
    
    leaderboard = results["leaderboard"]
    updated = any(r["rating"] != 1500.0 for r in leaderboard["candidates"])
    assert updated, "ELO ratings remained default"
    
    # Check verifiers exist in leaderboard
    assert len(leaderboard["verifiers"]) >= 3 # native + 2 proposed
    
    print("E2E Test passed successfully!")
