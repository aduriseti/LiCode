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
    def __init__(self, prompt: str, n_agents: int, budget: float, api_url: str = "http://127.0.0.1", model: str = "gemini-3-flash", provider: str = "opencode", agent_timeout: float = 300.0):
        self.run_id = f"run_{int(time.time())}"
        self.orchestrator = Orchestrator(prompt, n_agents, budget, base_dir=os.path.abspath(os.path.join("./.arenas", self.run_id)))
        self.arena_dir = self.orchestrator.base_dir
        self.sessions_dir = os.path.join(self.arena_dir, "sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
        
        rel_path = os.path.relpath(self.arena_dir, os.getcwd())
        print(f"Tournament Arena initialized at: {rel_path}")
        
        self.sharks: Dict[str, Shark] = {}
        self.agent_servers: Dict[str, subprocess.Popen] = {}
        self.price_history: List[Dict[str, float]] = [] 
        self.api_url = api_url
        self.model = model
        self.provider = provider
        self.agent_timeout = agent_timeout
        self.api_url = api_url # Store for UI
        
        self.log_buffer = deque(maxlen=20)
        self.port_lock = asyncio.Lock()

    async def initialize(self, json_logs: bool = False):
        """Async initialization of agent servers and sessions."""
        if not json_logs:
            logging.info(f"Initializing tournament for run_id: {self.run_id}")
            
        # 0. Initialize Orchestrator (clones workspaces in parallel)
        await self.orchestrator.initialize()

        async def setup_agent(aid):
            if not json_logs:
                logging.info(f"Starting setup for agent {aid}...")
            
            async with self.port_lock:
                port = self._find_free_port()
            
            agent_url = f"http://127.0.0.1:{port}"
            server_proc = await self._start_agent_server(aid, port)
            self.agent_servers[aid] = server_proc
            
            if not json_logs:
                logging.info(f"Server for {aid} started on port {port}. Initializing Shark...")

            # 2. Initialize Shark
            log_path = os.path.join(self.sessions_dir, f"{aid}.log")
            shark = Shark(aid, model=self.model, provider=self.provider, api_url=agent_url, log_path=log_path, timeout=self.agent_timeout)
            self.sharks[aid] = shark
            
            # 3. Create Session
            await shark.initialize_session()
            session_id = shark.session.id
            
            if not json_logs:
                logging.info(f"Session for {aid} initialized: {session_id}")

            # Emit init event for dashboard
            if json_logs:
                print(json.dumps({
                    "type": "agent_init", 
                    "agent_id": aid, 
                    "session_id": session_id,
                    "api_url": agent_url,
                    "arena_dir": self.arena_dir
                }))
                sys.stdout.flush()

            return aid, {
                "session_id": session_id,
                "api_url": agent_url,
                "log_path": os.path.relpath(shark.log_path, self.arena_dir) if shark.log_path else None
            }

        # Run setups concurrently
        tasks = [setup_agent(aid) for aid in self.orchestrator.state.agents.keys()]
        results = await asyncio.gather(*tasks)
        
        session_map = dict(results)

        if not json_logs:
            logging.info("All agents initialized.")

        # Emit Initial State
        if json_logs:
            print(json.dumps({
                "type": "state",
                **json.loads(self.orchestrator.state.to_json())
            }))
            sys.stdout.flush()

        # Write session map
        with open(os.path.join(self.arena_dir, "session_map.json"), "w") as f:
            json.dump(session_map, f, indent=2)

    def _find_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    async def _start_agent_server(self, agent_id: str, port: int) -> subprocess.Popen:
        """Starts a dedicated OpenCode server for a specific agent."""
        # Use the candidate worktree as the agent's workspace
        cand_id = agent_id.replace("agent", "cand")
        agent_dir = os.path.join(self.arena_dir, "worktrees", cand_id)
        
        # Ensure the directory exists (should be created by Orchestrator)
        if not os.path.exists(agent_dir):
            os.makedirs(agent_dir, exist_ok=True)
        
        real_home = os.path.expanduser('~')
        real_auth = os.path.join(real_home, ".local/share/opencode/auth.json")
        
        # Sandbox HOME inside the candidate worktree
        agent_home = os.path.join(agent_dir, ".home")
        arena_auth_dir = os.path.join(agent_home, ".local/share/opencode")
        os.makedirs(arena_auth_dir, exist_ok=True)
        
        if os.path.exists(real_auth):
            arena_auth_path = os.path.join(arena_auth_dir, "auth.json")
            if not os.path.exists(arena_auth_path):
                try:
                    os.symlink(real_auth, arena_auth_path)
                except FileExistsError:
                    pass
        
        env = os.environ.copy()
        env["HOME"] = agent_home
        
        agent_log = os.path.join(agent_dir, "opencode_serve.log")
        log_file = open(agent_log, "w")
        
        proc = subprocess.Popen(
            ["opencode", "serve", "--port", str(port), "--hostname=127.0.0.1"],
            stdout=log_file,
            stderr=log_file,
            cwd=agent_dir,
            env=env
        )
        
        # Wait for port to open
        start_time = time.time()
        while time.time() - start_time < 10:
            if proc.poll() is not None:
                raise RuntimeError(f"Server for {agent_id} failed to start.")
            try:
                # Async check for connection
                _, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.close()
                await writer.wait_closed()
                return proc
            except (ConnectionRefusedError, OSError):
                await asyncio.sleep(0.5)
        raise RuntimeError(f"Timed out waiting for server {agent_id} at port {port}")

    def _stop_servers(self):
        """Terminates all agent server processes."""
        for aid, proc in self.agent_servers.items():
            logging.info(f"Stopping server for {aid}...")
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.agent_servers.clear()

    async def run_loop(self, max_rounds: int, stream_ui: bool = True, json_logs: bool = False):
        """
        Executes the main game loop until convergence or max_rounds (Async).
        """
        if stream_ui and not json_logs:
            # Setup custom handler for dashboard + file logging
            log_file = os.path.join(self.arena_dir, "tournament.log")
            handler = BufferedLogHandler(self.log_buffer, log_file=log_file)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))
            logging.getLogger().addHandler(handler)

        if stream_ui and not json_logs:
            sys.stderr.write(f"Starting Tournament: {len(self.sharks)} Agents (Server: {self.api_url})\n")

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
                
                for action in actions:
                    if action.beliefs:
                        if json_logs:
                            print(json.dumps({
                                "type": "log", 
                                "message": f"Agent {action.agent_id} Beliefs: {action.beliefs}"
                            }))
                        else:
                            logging.info(f"Agent {action.agent_id} Beliefs: {action.beliefs}")
                
                if json_logs:
                    print(json.dumps({"type": "log", "message": f"Round {i+1}: All agents decided."}))
                else:
                    logging.info(f"Round {i+1}: All agents decided.")
                
                # 2. Step Market
                await self.orchestrator.process_round(list(actions))
                
                # 3. Update UI (Text Only)
                if not json_logs:
                    print(self.orchestrator.get_pretty_summary())
                elif json_logs:
                    # Output full state for dashboard
                    print(json.dumps({
                        "type": "state",
                        **json.loads(self.orchestrator.state.to_json())
                    }))
                    sys.stdout.flush()
                    
                # 4. Check Convergence
                if self.check_convergence():
                    if json_logs:
                        print(json.dumps({"type": "log", "message": f"Convergence reached at round {i+1}"}))
                    else:
                        logging.info(f"Convergence reached at round {i+1}")
                    break
        finally:
            pass
            
            # Close agents but keep servers alive for dashboard exploration
            close_tasks = [shark.close() for shark in self.sharks.values()]
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
            
        if json_logs:
             # Construct final output
            output = {
                "type": "final_result",
                "state": json.loads(self.orchestrator.state.to_json()),
                "report": self.orchestrator.get_final_report()
            }
            print(json.dumps(output))
        else:
            logging.info(f"Tournament finished. Agent servers remain active for dashboard exploration.")
        
        # DON'T stop servers - let them persist for dashboard
        # self._stop_servers()

    def check_convergence(self) -> bool:
        state = self.orchestrator.state
        current_prices = {
            k: state.get_asset_price(k) 
            for k, v in state.assets.items() if v.type == "CANDIDATE"
        }
        self.price_history.append(current_prices)
        if len(self.price_history) > 10:
            self.price_history.pop(0)
            
        converged = False
        
        # 1. Price Stability (Condition 1: Threshold 0.01)
        if len(self.price_history) >= 10:
            volatilities = []
            for cid in current_prices:
                prices = [h.get(cid, 0.5) for h in self.price_history]
                if len(prices) > 1:
                    volatilities.append(statistics.stdev(prices))
            if volatilities and statistics.mean(volatilities) < 0.01:
                logging.info("Convergence: Price Stability reached")
                converged = True

        wealths = [a.wealth for a in state.agents.values()]
        if not wealths: 
            converged = True 
        else:
            # 2. Wealth Concentration (Condition 2: Gini > 0.8)
            total_agent_wealth = sum(wealths)
            if total_agent_wealth > 0:
                # Gini calculation: sum_i sum_j |wi - wj| / (2 * n * sum(w))
                n = len(wealths)
                sum_diffs = sum(abs(wi - wj) for wi in wealths for wj in wealths)
                gini = sum_diffs / (2 * n * total_agent_wealth)
                if gini > 0.8:
                    logging.info(f"Convergence: Wealth Concentration reached (Gini: {gini:.2f})")
                    converged = True
                    
            # 3. Agent Bankruptcy (Condition 3: < 0.1 * B)
            if total_agent_wealth < 0.1 * self.orchestrator.budget:
                logging.info(f"Convergence: Agent Bankruptcy reached (Total Wealth: {total_agent_wealth:.2f})")
                converged = True

        # 4. Whale Bankruptcy (Condition 4: < 0.05 * B)
        if state.whale_wealth < 0.05 * self.orchestrator.budget:
            logging.info(f"Convergence: Whale Bankruptcy reached (Whale Wealth: {state.whale_wealth:.2f})")
            converged = True
        
        return converged