import asyncio
import json
import os
import sys
import time
import subprocess
import pytest
import aiohttp
import websocket

@pytest.mark.asyncio
async def test_dashboard_history_replay():
    """
    E2E test to verify that the dashboard replays event history to late-connecting clients.
    Uses websocket-client for the Socket.IO connection.
    """
    import tempfile
    import shutil
    
    # 1. Start a standalone dashboard process
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    
    dashboard_script = os.path.join(os.getcwd(), ".opencode", "lib", "dashboard-server.ts")
    env = os.environ.copy()
    env["DASHBOARD_PORT"] = str(port)
    
    process = await asyncio.create_subprocess_exec(
        "bun", dashboard_script,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    try:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=5)
        except asyncio.TimeoutError:
            pytest.fail("Dashboard failed to start within 5s")

        dashboard_url = f"http://127.0.0.1:{port}"
        
        # 2. Seed events
        async with aiohttp.ClientSession() as session:
            test_events = [
                {"type": "log", "message": "History test"},
                {"type": "agent_init", "agent_id": "test_agent", "api_url": "http://127.0.0.1:9999"},
                {"type": "state", "round_num": 1, "whale_wealth": 1000, "assets": {}, "agents": {}}
            ]
            for evt in test_events:
                async with session.post(f"{dashboard_url}/api/log", json=evt) as resp:
                    assert resp.status == 200

        # 3. Connect late
        ws_url = f"ws://127.0.0.1:{port}/socket.io/?EIO=4&transport=websocket"
        ws = websocket.create_connection(ws_url, timeout=2)
        ws.recv() # 0
        ws.send("40")
        ws.recv() # 40
        
        # 4. Verify replay
        received_types = set()
        start_time = time.time()
        while len(received_types) < 3 and (time.time() - start_time) < 5:
            try:
                ws.settimeout(1.0)
                msg = ws.recv()
                if msg.startswith('42'):
                    data = json.loads(msg[2:])
                    if isinstance(data, list) and data[0] == "log":
                        received_types.add(data[1].get("type"))
            except: break
        
        ws.close()
        assert "log" in received_types
        assert "agent_init" in received_types
        assert "state" in received_types
        
    finally:
        try:
            process.kill()
            await process.wait()
        except: pass

@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_agent_terminal_connection():
    """
    Replicates agent session connection and terminal reading (fibonacci check).
    Uses Playwright to fully simulate a late-connecting human opening the dashboard.
    """
    import tempfile
    import shutil
    from playwright.async_api import async_playwright
    
    # 1. Start tournament using market.cli directly (avoiding opencode wrapper browser opens)
    prompt = "run a tournament with 1 agent for 1 rounds to implement a function that returns the nth fibonacci number. Set log level to INFO."
    cmd = [
        sys.executable, "-m", "market.cli", "run",
        "--prompt", prompt,
        "--agents", "1",
        "--rounds", "1",
        "--dashboard",
        "--json-logs"
    ]
    
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    env["PYTHONUNBUFFERED"] = "1"
    
    # Needs a mock git repo to run locally
    temp_dir = tempfile.mkdtemp()
    subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
    with open(os.path.join(temp_dir, "dummy.txt"), "w") as f: f.write("dummy")
    subprocess.run(["git", "add", "dummy.txt"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=temp_dir, check=True, capture_output=True)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=temp_dir
    )
    
    try:
        dashboard_port = None
        # Extract dashboard URL from logs
        start_time = time.time()
        while not dashboard_port and (time.time() - start_time) < 30:
            try:
                line_bytes = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                if not line_bytes: break
                line = line_bytes.decode('utf-8').strip()
                if not line: continue
                if '"type": "log"' in line and "Dashboard active at http://localhost:" in line:
                    try:
                        data = json.loads(line)
                        msg = data.get("message", "")
                        dashboard_port = msg.split(":")[-1].strip()
                    except: continue
            except asyncio.TimeoutError:
                continue
        
        assert dashboard_port, "Dashboard port not found"
        
        # DELIBERATE LATE CONNECTION (Wait 15s for LLM progress)
        await asyncio.sleep(15)

        # 2. Use Playwright to visually verify the dashboard
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"])
            page = await browser.new_page()
            
            dashboard_url = f"http://127.0.0.1:{dashboard_port}"
            await page.goto(dashboard_url, wait_until="domcontentloaded", timeout=20000)
            
            # Wait for agent tab
            agent_tab = await page.wait_for_selector(".tab-button:not(#tab-system)", timeout=20000)
            await agent_tab.click()
                
            # Wait for terminal
            await page.wait_for_selector(".terminal-container.active .xterm-rows", timeout=10000)
            
            found = False
            expected_patterns = ["New session", "fibonacci", "attached"]
            
            start_time = time.time()
            while (time.time() - start_time) < 45:
                terminal_text = await page.evaluate("() => { const rows = document.querySelector('.terminal-container.active .xterm-rows'); return rows ? rows.textContent : ''; }")
                terminal_lower = terminal_text.lower()
                
                if any(p.lower() in terminal_lower for p in expected_patterns):
                    found = True
                    break
                
                if process.returncode is not None:
                    break
                await asyncio.sleep(2)
            
            await browser.close()
            assert found, f"Target content not found in UI terminal within 45s. Got: {terminal_text[:200]}"

    finally:
        try: 
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except: pass
        try: shutil.rmtree(temp_dir)
        except: pass

@pytest.mark.asyncio
@pytest.mark.timeout(120)
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
    import shutil
    
    # Use a tournament prompt that requires a tool call (modifying a file)
    cmd = [
        sys.executable, "-m", "market.cli", "run",
        "--prompt", "create a file named success.txt with content 'it worked'",
        "--agents", "1",
        "--rounds", "1",
        "--dashboard",
        "--json-logs"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    temp_dir = tempfile.mkdtemp()
    
    # Initialize a dummy git repository so the orchestrator can clone it
    subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
    with open(os.path.join(temp_dir, "dummy.txt"), "w") as f:
        f.write("dummy")
    subprocess.run(["git", "add", "dummy.txt"], cwd=temp_dir, check=True, capture_output=True)
    # Configure user name and email for the temp git repo to allow committing
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=temp_dir, check=True, capture_output=True)
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
                if "Dashboard active at http://localhost:" in line:
                    dashboard_url_found_stderr = True
            except: break

    try:
        # 1. Capture the URL from logs
        try:
            await asyncio.wait_for(
                asyncio.gather(read_stdout(), read_stderr()),
                timeout=40
            )
        except asyncio.TimeoutError:
            pass

        assert dashboard_url_found_stdout, "Dashboard URL not found in JSON (Stdout)"
        assert dashboard_url_found_stderr, "Dashboard URL not found in Text (Stderr)"
        assert len(captured_ports) > 0, "No ports captured from logs"

        # 2. Verify all Ports and Connectivity
        async with aiohttp.ClientSession() as session:
            for name, port in captured_ports:
                # A. Local connectivity
                local_url = f"http://127.0.0.1:{port}"
                try:
                    async with session.get(local_url, timeout=5) as response:
                        assert response.status == 200, f"Local {name} returned {response.status}"
                        if name == "Dashboard":
                            html = await response.text()
                            # Basic UI sanity check
                            assert 'id="top-pane"' in html, "Dashboard UI missing top-pane"
                except Exception as e:
                    pytest.fail(f"Local connectivity failed for {name}: {e}")

            # 3. Verify Trace Directory and Content
            # Wait a moment for background capture thread to write initial stream
            arena_dirs = [d for d in os.listdir(os.path.join(temp_dir, ".arenas")) if d.startswith("run_")]
            assert len(arena_dirs) > 0, "No arena run directory found"
            run_dir = os.path.join(temp_dir, ".arenas", arena_dirs[0])
            traces_dir = os.path.join(run_dir, "traces")
            
            assert os.path.exists(traces_dir), "Traces directory was not created"
            
            # Poll for trace content (capture thread might take a moment to start and flush)
            content = ""
            for _ in range(30): # Wait up to 30s for AI to think and act
                stream_traces = [f for f in os.listdir(traces_dir) if f.endswith("_stream.txt")]
                if stream_traces:
                    with open(os.path.join(traces_dir, stream_traces[0]), "r") as f:
                        content = f.read()
                        # Check if we have anything after [ASSISTANT]
                        if "[ASSISTANT]" in content:
                            parts = content.split("[ASSISTANT]")
                            if len(parts) > 1 and parts[1].strip():
                                break
                await asyncio.sleep(1.0)
            
            assert content, "No streaming trace content found after 30s polling"
            assert "[PROMPT]" in content, "Trace missing [PROMPT] header"
            assert "[ASSISTANT]" in content, "Trace missing [ASSISTANT] marker"
            
            # Check for AI thinking/content after the assistant marker
            assistant_content = content.split("[ASSISTANT]")[-1].strip()
            assert assistant_content, "No AI content found after [ASSISTANT] marker"
            
            # Verify tool usage is captured
            assert "[TOOL CALL:" in content, "Trace missing [TOOL CALL:] marker"
            assert "[TOOL RESULT:" in content, "Trace missing [TOOL RESULT:] marker"
            
            print(f"\n[VERIFIED] Streaming trace found with {len(content)} characters, including prompts and tools.")
            # 4. Persistence Check
            await session.close()
            await asyncio.sleep(7.0)
            
            if process.returncode is not None:
                # We expect return code 0 or -15/143 (terminated by us)
                if process.returncode not in [0, -15, 143]:
                    pytest.fail(f"Dashboard exited prematurely with code {process.returncode} after client disconnected.")    
    finally:
        # 3. Cleanup
        try:
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except: pass
        # try:
        #     shutil.rmtree(temp_dir)
        # except: pass

if __name__ == "__main__":
    try:
        asyncio.run(test_real_dashboard_startup())
    except Exception as e:
        sys.exit(1)
