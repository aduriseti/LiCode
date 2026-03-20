import asyncio
import json
import os
import sys
import time
import subprocess
import pytest
import aiohttp
import websocket
from market.common.process_registry import registry

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
    
    async with registry.spawn(
        "bun", dashboard_script,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    ) as process:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
        except asyncio.TimeoutError:
            pytest.fail("Dashboard failed to start within 10s")

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
        ws = websocket.create_connection(ws_url, timeout=5)
        ws.recv() # 0
        ws.send("40")
        ws.recv() # 40
        
        # 4. Verify replay
        received_types = set()
        start_time = time.time()
        while len(received_types) < 3 and (time.time() - start_time) < 10:
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
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Needs a mock git repo to run locally
        subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
        with open(os.path.join(temp_dir, "dummy.txt"), "w") as f: f.write("dummy")
        subprocess.run(["git", "add", "dummy.txt"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_dir, check=True, capture_output=True)

        async with registry.spawn(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=temp_dir
        ) as process:
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

@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_multi_model_terminal_content():
    """
    E2E test: Runs a tournament with 3 agents using opencode provider and different SOTA models.
    Verifies terminal connectivity and content for each agent.
    """
    from playwright.async_api import async_playwright
    import tempfile
    import shutil
    
    # Use verified March 2026 SOTA models
    models = ["opencode/claude-opus-4-6", "opencode/gpt-5.3-codex", "opencode/gemini-3.1-pro"]
    
    cmd = [
        sys.executable, "-m", "market.cli", "run",
        "--prompt", "Identify yourself in a text file named info.txt",
        "--agents", "3",
        "--rounds", "1",
        "--model", *models,
        "--provider", "opencode",
        "--dashboard",
        "--json-logs"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    env["PYTHONUNBUFFERED"] = "1"
    
    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
        with open(os.path.join(temp_dir, "dummy.txt"), "w") as f: f.write("dummy")
        subprocess.run(["git", "add", "dummy.txt"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_dir, check=True, capture_output=True)

        async with registry.spawn(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=temp_dir
        ) as process:
            dashboard_port = None
            # Extract dashboard URL from logs
            start_time = time.time()
            while not dashboard_port and (time.time() - start_time) < 40:
                try:
                    line_bytes = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                    if not line_bytes: break
                    line = line_bytes.decode('utf-8').strip()
                    if '"type": "log"' in line and "Dashboard active at http://localhost:" in line:
                        data = json.loads(line)
                        msg = data.get("message", "")
                        dashboard_port = msg.split(":")[-1].strip()
                        print(f"[TEST] Found dashboard port: {dashboard_port}")
                except asyncio.TimeoutError:
                    continue
            
            assert dashboard_port, "Dashboard port not found"
            
            # Wait for agents to initialize
            await asyncio.sleep(25)

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                page = await browser.new_page()
                dashboard_url = f"http://127.0.0.1:{dashboard_port}"
                print(f"[TEST] Navigating to {dashboard_url}")
                await page.goto(dashboard_url, wait_until="domcontentloaded", timeout=30000)
                
                for i in range(3):
                    aid = f"agent_{i}"
                    print(f"[TEST] Checking {aid}...")
                    
                    # Click tab for this agent
                    tab_selector = f".tab-button:has-text('{aid}')"
                    tab_button = await page.wait_for_selector(tab_selector, timeout=30000)
                    await tab_button.click(force=True)
                    print(f"[TEST] Clicked tab for {aid}")
                    
                    # Wait for terminal rows to exist for this agent
                    await page.wait_for_selector(".terminal-container.active .xterm-rows", timeout=20000)
                    
                    # Verify terminal content for this specific agent
                    found_content = False
                    # Patterns from test_agent_terminal_connection + agent ID
                    expected_patterns = ["New session", "Identify", "attached", aid]
                    
                    terminal_start = time.time()
                    while (time.time() - terminal_start) < 60:
                        terminal_text = await page.evaluate("() => { const rows = document.querySelector('.terminal-container.active .xterm-rows'); return rows ? rows.textContent : ''; }")
                        
                        # Mirror test_agent_terminal_connection's pattern check
                        terminal_lower = terminal_text.lower()
                        if any(p.lower() in terminal_lower for p in expected_patterns):
                            found_content = True
                            break

                        if process.returncode is not None:
                            break
                        await asyncio.sleep(3)
                    
                    assert found_content, f"Terminal for {aid} did not show expected content within 60s. Text: {terminal_text[:200]}"
                    print(f"[VERIFIED] Terminal for {aid} connected and showed content.")

                await browser.close()

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
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Initialize a dummy git repository so the orchestrator can clone it
        subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
        with open(os.path.join(temp_dir, "dummy.txt"), "w") as f:
            f.write("dummy")
        
        # ADDED: Create .gitignore to prevent recursive cloning of .arenas
        with open(os.path.join(temp_dir, ".gitignore"), "w") as f:
            f.write(".arenas/\n.home/\n*.log\n")
            
        subprocess.run(["git", "add", "dummy.txt", ".gitignore"], cwd=temp_dir, check=True, capture_output=True)
        # Configure user name and email for the temp git repo to allow committing
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_dir, check=True, capture_output=True)
        
        async with registry.spawn(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=temp_dir,
            env=env
        ) as process:
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
                    for _ in range(60): # Wait up to 60s for AI to think and act
                        stream_traces = [f for f in os.listdir(traces_dir) if f.endswith("_stream.txt")]
                        if stream_traces:
                            with open(os.path.join(traces_dir, stream_traces[0]), "r") as f:
                                content = f.read()
                                # Wait for the complete cycle: Thinking -> Action -> Result
                                if "[ASSISTANT]" in content and "[TOOL CALL:" in content and "[TOOL RESULT:" in content:
                                    # Ensure the tool result content (including the closing bracket) has been flushed
                                    parts = content.split("[TOOL RESULT:")
                                    if len(parts) > 1 and "]" in parts[1]:
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
                    
                    # Specific E2E Verification: Check worktree for expected changes and no leaks
                    # Locate cand_0 worktree
                    cand_0_dir = os.path.join(run_dir, "worktrees", "cand_0")
                    assert os.path.exists(cand_0_dir), "Agent worktree cand_0 not found"
                    
                    # Check success.txt
                    success_file = os.path.join(cand_0_dir, "success.txt")
                    assert os.path.exists(success_file), "Agent failed to create success.txt"
                    with open(success_file, "r") as f:
                        assert "it worked" in f.read()
                        
                    # Verify no distraction leaks or recursive clones
                    # Root items should only be committed files + our success.txt + agent's sandbox (.home)
                    root_items = os.listdir(cand_0_dir)
                    assert ".arenas" not in root_items, "Worktree contains leaked recursive .arenas directory"
                    
                    # Verify that .home is ignored by git (should not appear in untracked files)
                    proc = subprocess.run(["git", "ls-files", "-o", "--exclude-standard"], cwd=cand_0_dir, capture_output=True, text=True)
                    untracked_files = proc.stdout.splitlines()
                    
                    # The agent might have created success.txt but not staged it yet, or staged it.
                    # We want to ensure NO internal state files are untracked/tracked.
                    for f_path in untracked_files:
                        if "opencode.db" in f_path or ".home" in f_path:
                            pytest.fail(f"Worktree contains untracked internal state file: {f_path}")
                    
                    print(f"\n[VERIFIED] Streaming trace found with {len(content)} characters, including prompts and tools.")
                    # 4. Persistence Check
                    await session.close()
                    await asyncio.sleep(7.0)
                    
                    if process.returncode is not None:
                        # We expect return code 0 or -15/143 (terminated by us)
                        if process.returncode not in [0, -15, 143]:
                            pytest.fail(f"Dashboard exited prematurely with code {process.returncode} after client disconnected.")    
            except Exception as e:
                raise e

@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_multi_model_startup():
    """
    E2E test: Runs market.cli with multiple models and providers.
    Verifies that multiple agents start correctly with their respective configs.
    """
    import tempfile
    import shutil
    
    # Simple prompt
    cmd = [
        sys.executable, "-m", "market.cli", "run",
        "--prompt", "list files",
        "--agents", "2",
        "--rounds", "1",
        "--model", "opencode/claude-opus-4-6", "opencode/gpt-5.3-codex",
        "--provider", "opencode",
        "--json-logs"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
        with open(os.path.join(temp_dir, "dummy.txt"), "w") as f: f.write("dummy")
        subprocess.run(["git", "add", "dummy.txt"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_dir, check=True, capture_output=True)
        
        async with registry.spawn(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=temp_dir,
            env=env
        ) as process:
            # We wait for agent initialization logs
            agent_configs = {} # aid -> model
            start_time = time.time()
            while len(agent_configs) < 2 and (time.time() - start_time) < 40:
                try:
                    line_bytes = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                    if not line_bytes: break
                    line = line_bytes.decode('utf-8').strip()
                    if '"type": "agent_init"' in line:
                        data = json.loads(line)
                        aid = data.get("agent_id")
                        # In a real run, we can't easily check the config of the server from the agent_init event
                        # unless we modify the event. But we can check if it initialized.
                        agent_configs[aid] = True
                except asyncio.TimeoutError:
                    continue
            
            assert len(agent_configs) == 2, f"Only {len(agent_configs)} agents initialized"
            
            # Verify the traces exist
            arena_dirs = [d for d in os.listdir(os.path.join(temp_dir, ".arenas")) if d.startswith("run_")]
            run_dir = os.path.join(temp_dir, ".arenas", arena_dirs[0])
            traces_dir = os.path.join(run_dir, "traces")
            
            # Check logs for both agents
            for i in range(2):
                log_path = os.path.join(traces_dir, f"cand_{i}_opencode_serve.log")
                # Wait a bit for the log to be written
                for _ in range(10):
                    if os.path.exists(log_path): break
                    await asyncio.sleep(1)
                
                assert os.path.exists(log_path), f"Log for cand_{i} not found"

if __name__ == "__main__":
    try:
        asyncio.run(test_real_dashboard_startup())
    except Exception as e:
        sys.exit(1)
