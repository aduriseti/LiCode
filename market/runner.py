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
import signal
import contextlib
from typing import List, Dict, Optional, Union
from collections import deque

from .core.state import MarketState
from .orchestrator import Orchestrator, AgentAction
from .agents.shark import Shark
import market.common.process_registry  # Ensure global atexit sweeper is registered

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

class DashboardLogHandler(logging.Handler):
    """Forwards standard Python logs to the local dashboard UI."""
    def __init__(self, runner: 'MarketRunner'):
        super().__init__()
        self.runner = runner
        
    def emit(self, record):
        try:
            msg = self.format(record)
            # Use asyncio.run_coroutine_threadsafe to safely schedule the task
            # on the main event loop, since this might be called from worker threads (e.g. git clone).
            if hasattr(self.runner, 'main_loop') and self.runner.main_loop and self.runner.main_loop.is_running():
                import asyncio
                asyncio.run_coroutine_threadsafe(
                    self.runner._send_to_dashboard("/api/log", {"type": "log", "message": msg}),
                    self.runner.main_loop
                )
        except Exception:
            pass

from .common.server import start_opencode_server, find_free_port

class MarketRunner:
    """
    Manages the full lifecycle of a Logical Induction Tournament.
    Handles the game loop, agent orchestration, convergence checks,
    and the local OpenCode API server.
    """
    def __init__(self, prompt: str, n_agents: int, budget: float, api_url: Optional[str] = None, 
                 model: Union[str, List[str]] = "gemini-3-flash", 
                 provider: Union[str, List[str]] = "opencode", 
                 agent_timeout: float = 300.0, dashboard: bool = False,
                 max_retries: int = 3, initial_backoff: float = 120.0, 
                 max_backoff: float = 1000.0):
        self._exit_stack = contextlib.AsyncExitStack()
        self.run_id = f"run_{int(time.time())}"
        self.orchestrator = Orchestrator(prompt, n_agents, budget, base_dir=os.path.abspath(os.path.join("./.arenas", self.run_id)))
        self.arena_dir = self.orchestrator.base_dir
        self.sessions_dir = os.path.join(self.arena_dir, "sessions")
        self.traces_dir = os.path.join(self.arena_dir, "traces")
        os.makedirs(self.sessions_dir, exist_ok=True)
        os.makedirs(self.traces_dir, exist_ok=True)
        
        self.sharks: Dict[str, Shark] = {}
        self.agent_servers: Dict[str, asyncio.subprocess.Process] = {}
        self.price_history: List[Dict[str, float]] = [] 
        self.api_url = api_url
        
        # Standardize models and providers as lists
        self.models = [model] if isinstance(model, str) else list(model)
        self.providers = [provider] if isinstance(provider, str) else list(provider)
        
        self.agent_timeout = agent_timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.dashboard = dashboard
        self.dashboard_url = None
        self._http_session = None
        self.dashboard_proc = None
        self._dashboard_log_queue = []
        self._dashboard_flush_task = None
        self.main_loop = None
        
        self.log_buffer = deque(maxlen=20)
        self.port_lock = asyncio.Lock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # We don't call close() if the user wants to keep the dashboard open
        # but the CLI handles that by calling close() or not.
        # However, RAII says we should ALWAYS cleanup.
        # Actually, the user's prompt suggests they WANT cleanup.
        await self.close()

    async def _flush_dashboard_logs(self):
        if not self._dashboard_log_queue or not self.dashboard_url:
            return
        batch = list(self._dashboard_log_queue)
        self._dashboard_log_queue.clear()
        
        if self._http_session is None:
            import aiohttp
            self._http_session = aiohttp.ClientSession()
            
        try:
            async with self._http_session.post(f"{self.dashboard_url}/api/log", json={"type": "batch", "events": batch}) as resp:
                pass
        except Exception:
            pass

    async def _send_to_dashboard(self, endpoint: str, data: dict):
        if not self.dashboard or not self.dashboard_url:
            return
            
        if endpoint == "/api/log":
            self._dashboard_log_queue.append(data)
            if len(self._dashboard_log_queue) >= 50:
                await self._flush_dashboard_logs()
            else:
                if self._dashboard_flush_task is None or self._dashboard_flush_task.done():
                    async def flush_later():
                        await asyncio.sleep(0.1)
                        await self._flush_dashboard_logs()
                    if self.main_loop and self.main_loop.is_running():
                        self._dashboard_flush_task = self.main_loop.create_task(flush_later())
        else:
            if self._http_session is None:
                import aiohttp
                self._http_session = aiohttp.ClientSession()
            try:
                async with self._http_session.post(f"{self.dashboard_url}{endpoint}", json=data) as resp:
                    pass
            except Exception:
                pass

    async def initialize(self, json_logs: bool = False):
        """Async initialization of agent servers and sessions."""
        self.main_loop = asyncio.get_running_loop()
        
        rel_path = os.path.relpath(self.arena_dir, os.getcwd())
        if json_logs:
            print(json.dumps({"type": "log", "message": f"Tournament Arena initialized at: {rel_path}"}))
            sys.stdout.flush()
        else:
            print(f"Tournament Arena initialized at: {rel_path}")
        logging.info(f"Tournament Arena initialized at: {rel_path}")

        if self.dashboard:
            port = self._find_free_port()
            self.dashboard_url = f"http://localhost:{port}"
            
            # Use __file__ to reliably find the script regardless of CWD
            market_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(market_dir)
            dashboard_script = os.path.join(project_root, ".opencode", "lib", "dashboard-server.ts")
            
            env = os.environ.copy()
            env["DASHBOARD_PORT"] = str(port)
            
            dash_log_path = os.path.join(self.arena_dir, "dashboard_server.log")
            self.dash_log_file = open(dash_log_path, "w")

            # RAII Exception: We spawn dashboard directly via asyncio (NOT registry.spawn)
            # because we want it to be able to outlive the parent if a browser is connected.
            # The dashboard-server.ts handles its own auto-shutdown via stdin/timer.
            self.dashboard_proc = await asyncio.create_subprocess_exec(
                "bun", dashboard_script,
                env=env,
                stdout=self.dash_log_file,
                stderr=asyncio.subprocess.PIPE, # Capture stderr for diagnosis
                stdin=asyncio.subprocess.PIPE,
                limit=1024 * 1024 * 32,
                start_new_session=True
            )
            
            # Start a background task to proxy dashboard stderr for diagnosis
            async def proxy_dash_stderr():
                while self.dashboard_proc and self.dashboard_proc.returncode is None:
                    try:
                        line = await self.dashboard_proc.stderr.readline()
                        if not line: break
                        sys.stderr.write(f"[DASHBOARD ERROR] {line.decode('utf-8')}")
                        sys.stderr.flush()
                    except: break
            
            if self.main_loop and self.main_loop.is_running():
                self.main_loop.create_task(proxy_dash_stderr())
            
            # Start Heartbeat Task to keep stdin pipe alive
            async def dashboard_heartbeat():
                while self.dashboard_proc and self.dashboard_proc.returncode is None:
                    try:
                        if self.dashboard_proc.stdin and not self.dashboard_proc.stdin.is_closing():
                            self.dashboard_proc.stdin.write(b"heartbeat\n")
                            await self.dashboard_proc.stdin.drain()
                        else:
                            break
                    except (ConnectionResetError, BrokenPipeError):
                        break
                    except Exception:
                        break
                    await asyncio.sleep(2.0)
            
            if self.main_loop and self.main_loop.is_running():
                self.main_loop.create_task(dashboard_heartbeat())
            
            # Wait for ready (Increased to 150 attempts @ 0.1s = 15s)
            for _ in range(150):
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    
                    # Attach handler to forward Python logs to dashboard
                    dash_handler = DashboardLogHandler(self)
                    dash_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))
                    logging.getLogger().addHandler(dash_handler)
                    break
                except:
                    await asyncio.sleep(0.1)

            if json_logs:
                print(json.dumps({"type": "log", "message": f"Dashboard active at {self.dashboard_url}"}))
                sys.stdout.flush()
            else:
                sys.stderr.write(f"Dashboard active at {self.dashboard_url}\n")
                sys.stderr.flush()
            
            logging.info(f"Dashboard active at {self.dashboard_url}")

        logging.info(f"Initializing tournament for run_id: {self.run_id}")
            
        # 0. Initialize Orchestrator (clones workspaces in parallel)
        await self.orchestrator.initialize()

        # Run setups concurrently
        tasks = [self._setup_agent(aid, json_logs=json_logs) for aid in self.orchestrator.state.agents.keys()]
        results = await asyncio.gather(*tasks)
        
        # Filter out failed setups (None)
        session_map = {res[0]: res[1] for res in results if res is not None}

        logging.info(f"Initialized {len(self.sharks)} agents.")

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

    async def _setup_agent(self, aid: str, json_logs: bool = False):
        """Initializes a single agent with retries."""
        for attempt in range(3):
            try:
                logging.info(f"Starting setup for agent {aid} (Attempt {attempt+1}/3)...")
                
                # Determine model and provider for this specific agent
                try:
                    agent_idx = int(aid.split("_")[-1])
                except (ValueError, IndexError):
                    agent_idx = 0
                
                agent_model = self.models[agent_idx % len(self.models)]
                agent_provider = self.providers[agent_idx % len(self.providers)]
                
                async with self.port_lock:
                    port = self._find_free_port()
                
                agent_url = f"http://127.0.0.1:{port}"
                server_proc = await self._start_agent_server(aid, port, model=agent_model, provider=agent_provider)
                self.agent_servers[aid] = server_proc
                
                logging.info(f"Server for {aid} started on port {port} with {agent_provider}/{agent_model}. Initializing Shark...")

                # 2. Initialize Shark
                log_path = os.path.join(self.sessions_dir, f"{aid}.log")
                cand_id = aid.replace("agent", "cand")
                trace_path = os.path.join(self.traces_dir, f"{cand_id}_stream.txt")
                
                shark = Shark(aid, model=agent_model, provider=agent_provider, api_url=agent_url, 
                              log_path=log_path, timeout=self.agent_timeout, trace_path=trace_path,
                              max_retries=self.max_retries, initial_backoff=self.initial_backoff,
                              max_backoff=self.max_backoff)
                
                # 3. Create Session
                await shark.initialize_session()
                self.sharks[aid] = shark
                
                session_id = None
                if shark.session is not None and hasattr(shark.session, "id"):
                    session_id = str(shark.session.id)
                
                if session_id is None:
                    raise RuntimeError(f"Failed to initialize session for {aid}")
                
                logging.info(f"Session for {aid} initialized: {session_id}")

                # Emit init event for dashboard
                event = {
                    "type": "agent_init", 
                    "agent_id": aid, 
                    "session_id": session_id,
                    "api_url": agent_url,
                    "arena_dir": self.arena_dir
                }
                if json_logs:
                    print(json.dumps(event))
                    sys.stdout.flush()
                    
                await self._send_to_dashboard("/api/agent", event)
                await self._send_to_dashboard("/api/log", event)

                return aid, {
                    "session_id": session_id,
                    "api_url": agent_url,
                    "log_path": os.path.relpath(shark.log_path, self.arena_dir) if shark.log_path else None
                }
            except Exception as e:
                logging.error(f"Failed to setup agent {aid} on attempt {attempt+1}: {e}")
                # Cleanup if partially initialized
                if aid in self.sharks:
                    await self.sharks[aid].shutdown()
                    del self.sharks[aid]
                if aid in self.agent_servers:
                    proc = self.agent_servers[aid]
                    try:
                        import market.common.process_registry
                        await market.common.process_registry.registry.kill_process_tree(proc)
                    except:
                        try: proc.terminate()
                        except: pass
                    del self.agent_servers[aid]
                
                if attempt == 2:
                    logging.error(f"Agent {aid} failed setup after 3 attempts. Proceeding without it.")
                    return None

    def _find_free_port(self) -> int:
        return find_free_port()

    async def _start_agent_server(self, agent_id: str, port: int, model: str, provider: str) -> asyncio.subprocess.Process:
        cand_id = agent_id.replace("agent", "cand")
        agent_dir = os.path.join(self.arena_dir, "worktrees", cand_id)
        ctx = start_opencode_server(
            agent_id=cand_id, 
            agent_dir=agent_dir, 
            port=port, 
            model=model, 
            provider=provider, 
            traces_dir=self.traces_dir
        )
        return await self._exit_stack.enter_async_context(ctx)

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
                # 1. Collect Actions in Parallel
                logging.info(f"Round {i+1}: Collecting agent actions...")
                if json_logs:
                    print(json.dumps({"type": "log", "message": f"Starting Round {i+1}"}))
                    sys.stdout.flush()
                
                tasks = []
                agent_ids = []
                for aid, shark in self.sharks.items():
                    if aid in self.orchestrator.state.agents:
                        tasks.append(shark.get_action(self.orchestrator.state))
                        agent_ids.append(aid)
                
                # return_exceptions=True ensures one agent crash doesn't kill the tournament
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                actions = []
                for aid, result in zip(agent_ids, results):
                    if isinstance(result, Exception):
                        logging.error(f"Agent {aid} failed during action collection: {result}")
                        # Fallback to empty action
                        action = AgentAction(agent_id=aid, error=str(result))
                        actions.append(action)
                    else:
                        action = result
                        actions.append(action)
                        if result.beliefs:
                            logging.info(f"Agent {aid} Beliefs: {result.beliefs}")
                    
                    # Update state with failure info if present
                    if action.error:
                        portfolio = self.orchestrator.state.agents.get(aid)
                        if portfolio:
                            portfolio.failure_count += 1
                            portfolio.last_error = action.error
                        
                        # Report failure to dashboard
                        await self._send_to_dashboard("/api/log", {
                            "type": "agent_error",
                            "agent_id": aid,
                            "error": action.error,
                            "round": i + 1
                        })
                
                logging.info(f"Round {i+1}: All agents decided.")
                
                # 2. Step Market
                await self.orchestrator.process_round(list(actions))
                
                # 3. Update UI
                # Always send pretty summary to stderr for readability in bench logs
                sys.stderr.write(self.orchestrator.get_pretty_summary() + "\n")
                sys.stderr.flush()
                
                if not json_logs:
                    print(self.orchestrator.get_pretty_summary())
                
                # Report state to dashboard via HTTP
                if self.dashboard_url:
                    state_msg = {
                        "type": "state",
                        **json.loads(self.orchestrator.state.to_json())
                    }
                    await self._send_to_dashboard("/api/log", state_msg)
                    
                # 4. Check Convergence
                if self.check_convergence():
                    logging.info(f"Convergence reached at round {i+1}")
                    if json_logs:
                        print(json.dumps({"type": "log", "message": f"Convergence reached at round {i+1}"}))
                        sys.stdout.flush()
                    break
        finally:
            # 1. Shutdown Sharks (Abort sessions to stop token usage, but keep servers alive)
            close_tasks = [shark.shutdown() for shark in self.sharks.values()]
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
            
            # 2. Construct and Print Final Output
            output = {
                "type": "final_result",
                "state": self.orchestrator.state.to_dict(),
                "report": self.orchestrator.get_final_report()
            }
            if json_logs:
                print(json.dumps(output))
                sys.stdout.flush()
            
            await self._send_to_dashboard("/api/log", {"type": "log", "message": "Tournament Finished. Processing results..."})
            logging.info(f"Tournament finished. Agent servers remain active for dashboard exploration.")
            
            # 3. Final Dashboard Flush
            await self._flush_dashboard_logs()
            
            # 4. Stop Agent Servers (Disabled to allow dashboard browsing)
            # self._stop_servers()

    async def close(self):
        """Cleanly shutdown all remaining resources."""
        # 1. First, signal dashboard if it exists (close stdin so it can start inactivity timer)
        if self.dashboard_proc and self.dashboard_proc.stdin:
            try:
                self.dashboard_proc.stdin.close()
                await self.dashboard_proc.stdin.wait_closed()
            except:
                pass

        # 2. Cleanup all other RAII resources
        await self._exit_stack.aclose()
        
        if hasattr(self, "dash_log_file") and self.dash_log_file:
            try: self.dash_log_file.close()
            except: pass
        
        if self._http_session:
            await self._http_session.close()

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
