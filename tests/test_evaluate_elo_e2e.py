import os
import subprocess
import glob
import time
import json
import sys
import shutil
import pytest
import psutil

@pytest.mark.timeout(450)
def test_elo_tournament_e2e():
    """
    Runs an end-to-end test of the ELO tournament CLI with 4 agents.
    Verifies per-agent actions via structured JSON logs.
    """
    # Setup test parameters
    max_duration = 90
    num_agents = 4 # 2 candidates, 2 testers
    test_uuid = str(time.time())

    prompt = "Implement a function fib(n: int) -> int in a file named solution.py that returns the nth Fibonacci number (fib(0)=0, fib(1)=1)."

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
    env = os.environ.copy()
    env["LICODE_TEST_UUID"] = test_uuid
    
    # 1. Run Tournament with explicit timeout to prevent hangs
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=max_duration + 120)
    except subprocess.TimeoutExpired as e:
        print("Tournament TIMEOUT EXPIRED")
        print("STDOUT so far:", e.stdout if e.stdout else "")
        print("STDERR so far:", e.stderr if e.stderr else "")
        raise

    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

    # Give OS time to process kills
    time.sleep(5)

    # Check for process leaks using the UUID
    leaked_details = []
    leaked_procs = []
    for proc in psutil.process_iter(['pid', 'name', 'environ', 'cmdline']):
        try:
            p_env = proc.info.get('environ') or {}
            p_cmdline = proc.info.get('cmdline') or []
            if p_env.get("LICODE_TEST_UUID") == test_uuid or any(test_uuid in arg for arg in p_cmdline):
                details = f"PID {proc.info['pid']} ({proc.info['name']}): {' '.join(proc.info['cmdline'])}"
                leaked_details.append(details)
                leaked_procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Failsafe: Cleanup leaked processes before asserting so we don't leave the environment dirty
    for p in leaked_procs:
        try: p.kill()
        except: pass

    assert len(leaked_details) == 0, f"Tournament leaked processes with UUID {test_uuid}:\n" + "\n".join(leaked_details)
    assert result.returncode == 0, f"ELO CLI failed with code {result.returncode}"

    # Find newest run directory
    elo_runs = sorted(glob.glob(".arenas/elo_run_*"), key=os.path.getmtime, reverse=True)
    assert len(elo_runs) > 0
    latest_run_dir = os.path.abspath(elo_runs[0])

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
    candidate_ids = ["agent_0_cand", "agent_2_cand"]
    tester_ids = ["agent_1_test", "agent_3_test"]

    updates_by_cid = {e["data"]["candidate_id"] for e in events if e["type"] == "update_submitted"}
    
    # Extract proposers
    proposals = {e["data"]["id"] for e in events if e["type"] == "verifier_added"}
    proposers = set()
    for vid in proposals:
        # Expected format: test_agent_1_test_1712345678.diff
        if vid.startswith("test_agent_"):
            parts = vid.split("_")
            # Reconstruct agent_1_test
            agent_id = f"{parts[1]}_{parts[2]}_{parts[3]}"
            proposers.add(agent_id)

    print(f"Updates from: {updates_by_cid}")
    print(f"Tests from Agents: {proposers}")

    for cid in candidate_ids:
        assert cid in updates_by_cid, f"Candidate {cid} failed to submit an update. Found: {updates_by_cid}"

    for tid in tester_ids:
        assert tid in proposers, f"Tester {tid} failed to propose a test. Found: {proposers}"

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

    # 5. Verify Notebook Analysis (Regression)
    # This ensures the analysis notebook can process the results we just generated.
    notebook_path = os.path.abspath("notebooks/elo_analysis.ipynb")
    output_notebook = os.path.abspath(os.path.join(latest_run_dir, "executed_analysis.ipynb"))

    print(f"Verifying notebook analysis on: {latest_run_dir}")
    nb_cmd = [
        "jupyter", "nbconvert",
        "--to", "notebook",
        "--execute",
        "--ExecutePreprocessor.timeout=60",
        "--output", output_notebook,
        notebook_path
    ]

    nb_env = os.environ.copy()
    nb_env["ELO_RUN_DIR"] = latest_run_dir
    
    try:
        nb_result = subprocess.run(nb_cmd, capture_output=True, text=True, env=nb_env, timeout=120)
    except subprocess.TimeoutExpired:
        pytest.fail("Notebook execution timed out")

    if nb_result.returncode != 0:
        print("Notebook Execution STDOUT:", nb_result.stdout)
        print("Notebook Execution STDERR:", nb_result.stderr)
        
    assert nb_result.returncode == 0, f"Notebook execution failed with code {nb_result.returncode}"
    assert os.path.exists(output_notebook), "Executed notebook file not created"
    
    # Check for execution errors in cells
    with open(output_notebook, "r") as f:
        nb = json.load(f)
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            for output in cell.get("outputs", []):
                if output.get("output_type") == "error":
                    pytest.fail(f"Notebook Cell error: {output.get('ename')}: {output.get('evalue')}")

    print("E2E Test and Notebook Analysis passed successfully!")
