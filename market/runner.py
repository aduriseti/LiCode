import sys
import logging
import statistics
import subprocess
import time
import socket
import os
import shutil
import asyncio
import json
import glob
from typing import List, Dict, Optional
from collections import deque

from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.panel import Panel
from rich.console import Console
from rich import box
from rich.logging import RichHandler

from .core.state import MarketState
from .orchestrator import Orchestrator
from .agents.shark import Shark

class BufferedLogHandler(logging.Handler):
    def __init__(self, buffer: deque, log_file: Optional[str] = None):
        super().__init__()
        self.buffer = buffer
        self.file_handler = None
        if log_file:
            self.file_handler = logging.FileHandler(log_file)
            self.file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
    def emit(self, record):
        try:
            # Write to buffer for UI
            log_entry = self.format(record)
            self.buffer.append(log_entry)
            
            # Write to file if configured
            if self.file_handler:
                self.file_handler.emit(record)
                
        except Exception:
            self.handleError(record)

class MarketRunner:
    """
    Manages the full lifecycle of a Logical Induction Tournament.
    Handles the game loop, agent orchestration, convergence checks,
    and the local OpenCode API server.
    """
    def __init__(self, prompt: str, n_agents: int, budget: float, api_url: str = "http://127.0.0.1", model: str = "gemini-3-flash", provider: str = "opencode", target_file: Optional[str] = None, agent_timeout: float = 300.0):
        # ... existing init ...
        # Create Arena directory
        self.arena_dir = os.path.abspath(f"./.arenas/run_{int(time.time())}")
        os.makedirs(self.arena_dir, exist_ok=True)
        
        # Create sessions directory for logs
        self.sessions_dir = os.path.join(self.arena_dir, "sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
        
        # Log relative path for user
        rel_path = os.path.relpath(self.arena_dir, os.getcwd())
        # Use basic print before rich is set up
        print(f"Tournament Arena initialized at: {rel_path}")
        
        self.orchestrator = Orchestrator(prompt, n_agents, budget, base_dir=self.arena_dir, target_file=target_file)
        self.sharks: Dict[str, Shark] = {}
        self.price_history: List[Dict[str, float]] = [] 
        self.server_process = None
        self.api_url = api_url
        self.model = model
        self.provider = provider
        
        # Log buffer for dashboard
        self.log_buffer = deque(maxlen=20)
        
        # 1. Start Server if not external URL
        if "127.0.0.1" in api_url or "localhost" in api_url:
            self.port = self._find_free_port()
            self.api_url = f"http://127.0.0.1:{self.port}"
            self._start_server()

        # 2. Initialize Sharks
        for aid in self.orchestrator.state.agents.keys():
            log_path = os.path.join(self.sessions_dir, f"{aid}.log")
            shark = Shark(aid, model=model, provider=provider, api_url=self.api_url, log_path=log_path, timeout=agent_timeout)
            self.sharks[aid] = shark

        # 3. Emit Initial State
        print(json.dumps({
            "type": "state",
            **json.loads(self.orchestrator.state.to_json())
        }))
        sys.stdout.flush()

    # ... existing methods ...
    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    def _start_server(self):
        # Notify user how to attach (print to stderr for immediate visibility)
        attach_cmd = f"opencode attach http://127.0.0.1:{self.port}"
        sys.stderr.write(f"\n[Tournament] Server started. To inspect agents, run in NEW terminal:\n{attach_cmd}\n\n")
        
        # Hybrid Approach: Sandbox HOME but link Auth
        real_home = os.environ.get("HOME", "/home/codespace")
        real_auth = os.path.join(real_home, ".local/share/opencode/auth.json")
        
        # Setup Arena Home
        arena_auth_dir = os.path.join(self.arena_dir, ".local/share/opencode")
        os.makedirs(arena_auth_dir, exist_ok=True)
        
        if os.path.exists(real_auth):
            arena_auth_path = os.path.join(arena_auth_dir, "auth.json")
            if not os.path.exists(arena_auth_path):
                os.symlink(real_auth, arena_auth_path)
        
        server_env = os.environ.copy()
        server_env["HOME"] = self.arena_dir
        
        self.server_process = subprocess.Popen(
            ["opencode", "serve", "--port", str(self.port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=self.arena_dir,
            env=server_env
        )
        
        start_time = time.time()
        while time.time() - start_time < 10:
            if self.server_process.poll() is not None:
                raise RuntimeError("OpenCode server failed to start immediately.")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                    return
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.5)
        raise RuntimeError("Timed out waiting for OpenCode server to start.")

    def _render_dashboard(self) -> Layout:
        """Generates the Rich layout for the dashboard."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=2),
            Layout(name="logs", ratio=1),
            Layout(name="footer", size=3)
        )
        
        layout["header"].update(Panel(f"Round {self.orchestrator.state.round_num} | Agents: {len(self.sharks)} | Whale Wealth: {self.orchestrator.state.whale_wealth:.2f}", title="Logical Induction Market"))
        
        # Split main into Assets and Agents
        layout["main"].split_row(
            Layout(name="assets"),
            Layout(name="agents")
        )
        
        # Assets Table
        asset_table = Table(title="Market Assets", box=box.SIMPLE)
        asset_table.add_column("ID")
        asset_table.add_column("Type")
        asset_table.add_column("Price")
        asset_table.add_column("Status")
        
        sorted_ids = sorted(self.orchestrator.state.assets.keys(), key=lambda x: (self.orchestrator.state.assets[x].type, x))
        for aid in sorted_ids:
            asset = self.orchestrator.state.assets[aid]
            p = self.orchestrator.state.get_asset_price(aid)
            bar_len = int(p * 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            asset_table.add_row(
                aid, 
                asset.type, 
                f"{p:.3f}", 
                bar
            )
        layout["assets"].update(Panel(asset_table))
        
        # Agents Table
        agent_table = Table(title="Agent Wealth", box=box.SIMPLE)
        agent_table.add_column("Agent")
        agent_table.add_column("Wealth")
        
        sorted_agents = sorted(self.orchestrator.state.agents.values(), key=lambda a: a.wealth, reverse=True)
        for agent in sorted_agents:
            agent_table.add_row(agent.agent_id, f"{agent.wealth:.2f}")
            
        layout["agents"].update(Panel(agent_table))
        
        # Logs Panel
        log_text = "\n".join(self.log_buffer)
        layout["logs"].update(Panel(log_text, title="Event Log", box=box.SIMPLE))
        
        attach_cmd = f"opencode attach {self.api_url}"
        layout["footer"].update(Panel(f"Server: {self.api_url} | Attach: [bold cyan]{attach_cmd}[/]", style="dim"))
        
        return layout

    async def run_loop(self, max_rounds: int, stream_ui: bool = True, json_logs: bool = False):
        """
        Executes the main game loop until convergence or max_rounds (Async).
        """
        try:
            if stream_ui and not json_logs:
                # Setup custom handler for dashboard + file logging
                log_file = os.path.join(self.arena_dir, "tournament.log")
                handler = BufferedLogHandler(self.log_buffer, log_file=log_file)
                handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))
                logging.getLogger().addHandler(handler)

            # Initialize all sessions first to get IDs
            session_map = {}
            for aid, shark in self.sharks.items():
                await shark.initialize_session()
                # Compute relative path to log for user convenience
                rel_log_path = os.path.relpath(shark.log_path, self.arena_dir) if shark.log_path else None
                
                # Find session file
                session_file = None
                session_id = shark.session.id
                # Search in arena_dir/.local/share/opencode/storage/session/*/<session_id>.json
                search_pattern = os.path.join(self.arena_dir, ".local/share/opencode", "storage", "session", "*", f"{session_id}.json")
                matches = glob.glob(search_pattern)
                if matches:
                    session_file = os.path.relpath(matches[0], self.arena_dir)

                session_map[aid] = {
                    "session_id": session_id,
                    "session_file": session_file,
                    "log_path": rel_log_path
                }
                if json_logs:
                    print(json.dumps({"type": "agent_init", "agent_id": aid, "session_id": session_id}))
                else:
                    logging.info(f"Agent {aid} connected with session: {shark.session.id}")
            
            # Add metadata
            session_map["_meta"] = {
                "server_url": self.api_url,
                "arena_dir": self.arena_dir,
                "command_to_attach": f"opencode attach {self.api_url}"
            }
            
            # Write session map for user
            with open(os.path.join(self.arena_dir, "session_map.json"), "w") as f:
                json.dump(session_map, f, indent=2)

            if stream_ui and not json_logs:
                sys.stderr.write(f"Starting Tournament: {len(self.sharks)} Agents (Server: {self.api_url})\n")

            # Use Rich Live Display if stream_ui is True
            # Force terminal to ensure Rich renders control codes through the pipe
            if stream_ui and not json_logs:
                console = Console(stderr=True, force_terminal=True)
                live = Live(self._render_dashboard(), refresh_per_second=4, console=console, transient=False)
                live.start()
            else:
                live = None

            try:
                for i in range(max_rounds):
                    # ... existing loop logic ...
                    # 1. Collect Actions in Parallel
                    if json_logs:
                        print(json.dumps({"type": "log", "message": f"Round {i+1}: Collecting agent actions..."}))
                    else:
                        logging.info(f"Round {i+1}: Collecting agent actions...")
                    
                    tasks = []
                    for aid, shark in self.sharks.items():
                        if aid in self.orchestrator.state.agents:
                            tasks.append(shark.get_action(self.orchestrator.state))
                    
                    actions = await asyncio.gather(*tasks)
                    
                    if json_logs:
                        print(json.dumps({"type": "log", "message": f"Round {i+1}: All agents decided."}))
                    else:
                        logging.info(f"Round {i+1}: All agents decided.")
                    
                    # 2. Step Market
                    self.orchestrator.process_round(list(actions))
                    
                    # 3. Update UI
                    if live:
                        live.update(self._render_dashboard())
                    elif json_logs:
                        # Output full state for dashboard
                        print(json.dumps({
                            "type": "state",
                            **json.loads(self.orchestrator.state.to_json())
                        }))
                        sys.stdout.flush()
                        
                    # 4. Check Convergence
                    if self.check_convergence():
                        if live:
                            # sys.stderr.write(f"Convergence Reached at Round {i+1}!\n")
                            # Just let the live display persist
                            pass
                        elif json_logs:
                            print(json.dumps({"type": "log", "message": f"Convergence reached at round {i+1}"}))
                        else:
                            logging.info(f"Convergence reached at round {i+1}")
                        break
            finally:
                if live:
                    live.stop()
                
            if json_logs:
                 # Construct final output
                output = {
                    "type": "final_result",
                    "state": json.loads(self.orchestrator.state.to_json()),
                    "report": self.orchestrator.get_final_report()
                }
                print(json.dumps(output))
            else:
                logging.info(f"Tournament finished. Final report generated in {self.arena_dir}")
        finally:
            self._stop_server()

    def _stop_server(self):
        if self.server_process:
            logging.info("Stopping OpenCode server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            self.server_process = None

    def check_convergence(self) -> bool:
        state = self.orchestrator.state
        current_prices = {
            k: state.get_asset_price(k) 
            for k, v in state.assets.items() if v.type == "CANDIDATE"
        }
        self.price_history.append(current_prices)
        if len(self.price_history) > 10:
            self.price_history.pop(0)
            
        if len(self.price_history) >= 5:
            volatilities = []
            for cid in current_prices:
                prices = [h.get(cid, 0.5) for h in self.price_history]
                if len(prices) > 1:
                    volatilities.append(statistics.stdev(prices))
            if volatilities and statistics.mean(volatilities) < 0.005:
                return True

        wealths = [a.wealth for a in state.agents.values()]
        if not wealths: return True 
        
        total_agent_wealth = sum(wealths)
        if total_agent_wealth > 0:
            max_wealth = max(wealths)
            if max_wealth / total_agent_wealth > 0.8:
                return True
                
        if total_agent_wealth < 50.0:
            return True
            
        return False