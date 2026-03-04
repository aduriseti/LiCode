import asyncio
import json
import os
import sys
import time
import subprocess
import pytest
import aiohttp

@pytest.mark.asyncio
async def test_real_dashboard_startup():
    """
    E2E test: Runs market.cli with a real dashboard process (NO MOCKING).
    Verifies:
    1. Dashboard logs its URL to stdout (JSON) and stderr (Text).
    2. Local dashboard is responsive (127.0.0.1).
    3. Dashboard UI structure is correct (panes loading).
    4. All agent ports are functional locally.
    """
    import tempfile
    
    # Use a minimal tournament
    cmd = [
        sys.executable, "-m", "market.cli", "run",
        "--prompt", "return 42",
        "--agents", "1",
        "--rounds", "1",
        "--dashboard",
        "--json-logs"
    ]
    
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    import shutil
    temp_dir = tempfile.mkdtemp()
    
    # Initialize a dummy git repository so the orchestrator can clone it
    subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
    with open(os.path.join(temp_dir, "dummy.txt"), "w") as f:
        f.write("dummy")
    subprocess.run(["git", "add", "dummy.txt"], cwd=temp_dir, check=True, capture_output=True)
    # Configure user name and email for the temp git repo to allow committing
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=temp_dir, check=True, capture_output=True)
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=temp_dir,
        env=env
    )
    
    dashboard_url_found_stdout = False
    dashboard_url_found_stderr = False
    captured_ports = [] # List of (name, port)
    
    async def read_stdout():
        nonlocal dashboard_url_found_stdout, captured_ports
        while True:
            try:
                line_bytes = await process.stdout.readline()
                if not line_bytes: break
                line = line_bytes.decode('utf-8').strip()
                
                # Capture Dashboard Port
                if '"type": "log"' in line and "Dashboard active at http://localhost:" in line:
                    dashboard_url_found_stdout = True
                    try:
                        data = json.loads(line)
                        msg = data.get("message", "")
                        port = msg.split(":")[-1].strip()
                        captured_ports.append(("Dashboard", port))
                    except: pass
                
                # Capture Agent Ports
                if '"type": "agent_init"' in line:
                    try:
                        data = json.loads(line)
                        port = data.get("api_url", "").split(":")[-1].strip()
                        captured_ports.append((f"Agent {data.get('agent_id')}", port))
                    except: pass
            except: break

    async def read_stderr():
        nonlocal dashboard_url_found_stderr
        while True:
            try:
                line_bytes = await process.stderr.readline()
                if not line_bytes: break
                line = line_bytes.decode('utf-8', errors='replace').strip()
                print(f"[STDERR] {line}")
                if "Dashboard active at http://localhost:" in line:
                    dashboard_url_found_stderr = True
            except: break

    try:
        # 1. Capture the URL from logs
        try:
            await asyncio.wait_for(
                asyncio.gather(read_stdout(), read_stderr()),
                timeout=20
            )
        except asyncio.TimeoutError:
            pass

        assert dashboard_url_found_stdout, "Dashboard URL not found in JSON (Stdout)"
        assert dashboard_url_found_stderr, "Dashboard URL not found in Text (Stderr)"
        assert len(captured_ports) > 0, "No ports captured from logs"

        # 2. Verify all Ports and Connectivity
        async with aiohttp.ClientSession() as session:
            for name, port in captured_ports:
                print(f"\n--- Verifying {name} (Port {port}) ---")
                
                # A. Local connectivity
                local_url = f"http://127.0.0.1:{port}"
                print(f"  Local Check: {local_url}")
                try:
                    async with session.get(local_url, timeout=5) as response:
                        assert response.status == 200, f"Local {name} returned {response.status}"
                        if name == "Dashboard":
                            html = await response.text()
                            # Basic UI sanity check
                            assert 'id="top-pane"' in html, "Dashboard UI missing top-pane"
                        print(f"  SUCCESS: {name} is healthy on local interface.")
                except Exception as e:
                    pytest.fail(f"Local connectivity failed for {name}: {e}")

            # 3. Persistence Check (NEW)
            # Close the current session/client and verify the process doesn't exit immediately
            # (Dashboard should stay alive while this parent process is alive)
            await session.close()
            print("\nVerifying Dashboard Persistence (waiting 7s)...")
            await asyncio.sleep(7.0)
            
            if process.returncode is not None:
                pytest.fail(f"Dashboard exited prematurely with code {process.returncode} after client disconnected.")
            else:
                print("SUCCESS: Dashboard persisted after client disconnect.")
    
    finally:
        # 3. Cleanup
        try:
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except: pass
        try:
            shutil.rmtree(temp_dir)
        except: pass

if __name__ == "__main__":
    # If run as a script, execute and print results
    try:
        asyncio.run(test_real_dashboard_startup())
        print("\nOVERALL SUCCESS: Dashboard and Agents are functional locally!")
    except Exception as e:
        print(f"\nOVERALL FAILURE: {e}")
        sys.exit(1)
