import json
import logging
import os
import asyncio
import time
from enum import Enum, StrEnum
from typing import Dict, Any, Optional, List, Tuple, Union
from opencode_ai import AsyncOpencode, APITimeoutError, APIConnectionError
from opencode_ai.types import (
    TextPart, 
    ToolPart,
    ToolStateRunning,
    ToolStateCompleted
)
from opencode_ai.types.event_list_response import EventMessagePartUpdated
from chompjs import parse_js_objects
from json_repair import loads as repair_loads

class AgentState(StrEnum):
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    THINKING = "thinking"
    WAITING = "waiting"
    ERROR = "error"
    TERMINATED = "terminated"

class AgentType(StrEnum):
    CANDIDATE = "candidate"
    TESTER = "tester"
    SHARK = "shark"

class AgentActionType(StrEnum):
    UPDATE_CANDIDATE = "update_candidate"
    PROPOSE_TEST = "propose_test"
    PROPOSE_VERIFIER = "VERIFIER" # For Shark JSON consistency

class InterruptType(StrEnum):
    RIVAL_UPDATE = "rival_update"
    FAILURE_NOTIFICATION = "failure_notification"
    GENERIC = "generic"

class LLMResponseError(Exception):
    """Raised when the LLM returns an invalid or non-JSON response."""
    pass

class FatalAgentError(Exception):
    """Raised for critical agent failures that should stop the tournament."""
    pass

class BaseAgent:
    """
    Base class for robust OpenCode agents with a formal state machine.
    Provides core API and session management logic.
    """
    def __init__(self, agent_id: str, model: str, provider: str, 
                 api_url: str, timeout: float = 300.0,
                 log_path: Optional[str] = None, trace_path: Optional[str] = None,
                 max_retries: int = 3, max_backoff: float = 1000.0):
        self.agent_id = agent_id
        self.model = model
        self.provider = provider
        self.api_url = api_url
        self.timeout = timeout
        self.log_path = log_path
        self.trace_path = trace_path
        self.max_retries = max_retries
        self.max_backoff = max_backoff
        
        self.state = AgentState.UNINITIALIZED
        self.client = AsyncOpencode(base_url=api_url, timeout=timeout, max_retries=0)
        self.session = None

    def _transition(self, target_state: AgentState):
        """Standardized state transition logging."""
        if self.state == target_state:
            return
        logging.info(f"AGENT_STATE: {self.agent_id}: {self.state.value} -> {target_state.value}")
        self.state = target_state

    async def initialize_session(self, system_prompt: str = ""):
        """Async initialization of the OpenCode session."""
        if not self.session:
            self._transition(AgentState.INITIALIZING)
            self.session = await self.client.session.create(extra_body={})
            if not hasattr(self.session, 'id'):
                self._transition(AgentState.ERROR)
                raise RuntimeError(f"Failed to create session for agent {self.agent_id}. Got: {self.session}")
            
            if self.log_path:
                os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
                with open(self.log_path, "a") as f:
                    f.write(f"=== Session Created: {self.session.id} ===\n")
                    if system_prompt:
                        f.write(f"=== SYSTEM PROMPT ===\n{system_prompt}\n=====================\n")

    def _append_to_trace(self, content: str):
        """Helper for thread-safe file appending to the stream trace."""
        if not self.trace_path:
            return
        try:
            os.makedirs(os.path.dirname(self.trace_path), exist_ok=True)
            with open(self.trace_path, "a") as f:
                f.write(content)
                f.flush()
        except Exception:
            pass

    async def chat_robust(self, prompt: str, system_prompt: str, timeout: Optional[float] = None) -> str:
        """
        Sends a message with trace capture and state management.
        """
        if self.state == AgentState.TERMINATED:
            return "{}"
            
        if not self.session:
            await self.initialize_session(system_prompt)
            
        self._transition(AgentState.THINKING)
        call_timeout = timeout or self.timeout
        
        if self.trace_path:
            await asyncio.to_thread(self._append_to_trace, f"\n\n[SYSTEM PROMPT]\n{system_prompt}\n\n[PROMPT]\n{prompt}\n\n[ASSISTANT]\n")

        part_lengths = {}
        seen_tool_parts = set()
        stream_text_chunks = []

        try:
            stream = await self.client.event.list()
            
            chat_task = asyncio.create_task(self.client.session.chat(
                id=self.session.id,
                model_id=self.model,
                provider_id=self.provider,
                system=system_prompt,
                parts=[{"type": "text", "text": prompt}],
                timeout=call_timeout
            ))
            
            async def consume_stream():
                try:
                    async for event in stream:
                        if isinstance(event, EventMessagePartUpdated):
                            part = event.properties.part
                            if part.session_id == self.session.id:
                                if isinstance(part, TextPart):
                                    last_len = part_lengths.get(part.id, 0)
                                    delta = part.text[last_len:]
                                    if delta:
                                        stream_text_chunks.append(delta)
                                        await asyncio.to_thread(self._append_to_trace, delta)
                                        part_lengths[part.id] = len(part.text)
                                elif isinstance(part, ToolPart):
                                    state = part.state
                                    status = state.status
                                    key = f"{part.id}-{status}"
                                    if key not in seen_tool_parts:
                                        seen_tool_parts.add(key)
                                        if isinstance(state, ToolStateRunning):
                                            await asyncio.to_thread(self._append_to_trace, f"\n[TOOL CALL: {part.tool}({state.input})]\n")
                                        elif isinstance(state, ToolStateCompleted):
                                            await asyncio.to_thread(self._append_to_trace, f"\n[TOOL RESULT: {str(state.output)[:500]}...]\n")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logging.debug(f"Trace stream consumer error: {e}")

            consumer_task = asyncio.create_task(consume_stream())
            
            try:
                chat_response = await chat_task
                await asyncio.sleep(0.8) 
            finally:
                consumer_task.cancel()
                try: await consumer_task
                except asyncio.CancelledError: pass
                await stream.close()

            content = "".join(stream_text_chunks)
            if not content and chat_response and hasattr(chat_response, "parts"):
                extracted_text = []
                for part in chat_response.parts:
                    if isinstance(part, TextPart):
                        extracted_text.append(part.text)
                content = "".join(extracted_text)
            
            if not content:
                has_tools = any(isinstance(part, ToolPart) for part in getattr(chat_response, "parts", []))
                if has_tools:
                    return "{}"
                raise LLMResponseError(f"Received empty response from agent {self.agent_id}.")

            return content

        except (FatalAgentError, APITimeoutError, APIConnectionError):
            raise
        except Exception as e:
            err_str = str(e)
            if "Expecting value" in err_str or "JSONDecodeError" in type(e).__name__:
                raise APIConnectionError(request=None)
            self._transition(AgentState.ERROR)
            raise FatalAgentError(f"API call failed for {self.agent_id}: {e}")

    def parse_json_action(self, content: str, required_keys: List[str]) -> Dict[str, Any]:
        """resiliently parses JSON from LLM text."""
        try:
            candidates = list(parse_js_objects(content))
            if not candidates:
                repaired = repair_loads(content)
                if isinstance(repaired, dict):
                    candidates = [repaired]
            
            for cand in reversed(candidates):
                if isinstance(cand, dict) and any(k in cand for k in required_keys):
                    return cand
            
            raise LLMResponseError(f"Response missing required keys {required_keys}.")
        except Exception as e:
            if isinstance(e, LLMResponseError): raise e
            raise LLMResponseError(f"Invalid JSON format: {str(e)}")

    async def interrupt(self):
        """Generic abort command."""
        try:
            if self.session and hasattr(self.session, "id"):
                await self.client.session.abort(id=self.session.id)
        except Exception:
            pass

    async def shutdown(self):
        """Cleanly closes agent resources."""
        self._transition(AgentState.TERMINATED)
        await self.interrupt()
        await self.client.close()

class EloAgent(BaseAgent):
    """
    Base class for ELO agents. Handles server management and common action loop logic.
    """
    def __init__(self, agent_id: str, worktree_dir: str, agent_type: AgentType,
                 model: str = "gemini-3-flash", provider: str = "opencode", traces_dir: str = "/tmp",
                 orchestrator: Any = None):
        log_path = os.path.join(worktree_dir, f"{agent_id}.log")
        trace_path = os.path.join(traces_dir, f"{agent_id}_stream.txt")
        
        super().__init__(
            agent_id=agent_id, model=model, provider=provider, api_url="http://127.0.0.1:4096",
            timeout=300.0, log_path=log_path, trace_path=trace_path
        )
        self.worktree_dir = worktree_dir
        self.agent_type = agent_type
        self.orchestrator = orchestrator
        self.process: Optional[asyncio.subprocess.Process] = None
        self.port: Optional[int] = None
        self._loop_task: Optional[asyncio.Task] = None

    def _get_system_prompt(self) -> str:
        """Leaf classes must implement this."""
        raise NotImplementedError("EloAgent is a base class. Use CandidateAgent or TesterAgent.")

    async def start(self, initial_prompt: str):
        """Starts the headless server and begins the action loop."""
        from market.common.server import start_opencode_server, find_free_port
        logging.info(f"Starting session for {self.agent_type.value} agent {self.agent_id}")
        self.port = find_free_port()
        self.client = AsyncOpencode(base_url=f"http://127.0.0.1:{self.port}", timeout=self.timeout, max_retries=0)
        
        # RAII: Use the server context manager
        self._server_cm = start_opencode_server(
            agent_id=self.agent_id,
            agent_dir=self.worktree_dir,
            port=self.port,
            model=self.model,
            provider=self.provider,
            traces_dir=os.path.dirname(self.trace_path) if self.trace_path else "/tmp"
        )
        self.process = await self._server_cm.__aenter__()
        
        await self.initialize_session(self._get_system_prompt())
        self._loop_task = asyncio.create_task(self._run_loop(initial_prompt))

    async def _handle_action(self, action: str, data: Dict[str, Any]) -> str:
        """Leaf classes must implement specific action handling."""
        raise NotImplementedError()

    async def _run_loop(self, current_prompt: str):
        """Continuous action loop."""
        system_prompt = self._get_system_prompt()
        while self.state != AgentState.TERMINATED:
            try:
                content = await self.chat_robust(current_prompt, system_prompt=system_prompt)
                try:
                    data = self.parse_json_action(content, ["action"])
                    action = data.get("action")
                    current_prompt = await self._handle_action(action, data)
                except LLMResponseError as e:
                    logging.warning(f"Agent {self.agent_id} parsing failed: {e}")
                    current_prompt = f"ERROR: Your response was invalid: {str(e)}\nYou MUST output your final decision as a JSON object in your FINAL TEXT RESPONSE (not via a tool)."
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Agent {self.agent_id} loop error: {e}")
                await asyncio.sleep(5)

    async def interrupt(self, message: Optional[str] = None, data: Optional[Dict] = None):
        """The Pivot: Interrupt current thinking or waiting and restart with new data."""
        if data and self.worktree_dir:
            interrupts_dir = os.path.join(self.worktree_dir, ".interrupts")
            os.makedirs(interrupts_dir, exist_ok=True)
            filepath = os.path.join(interrupts_dir, f"interrupt_{int(time.time() * 1000)}.json")
            with open(filepath, "w") as f:
                json.dump({"message": message, "data": data}, f, indent=2)

        await super().interrupt()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()

        if message and self.state != AgentState.TERMINATED:
            self._transition(AgentState.THINKING)
            self._loop_task = asyncio.create_task(self._run_loop(message))

    async def shutdown(self):
        """Stops the loop and server."""
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
        await super().shutdown()
        
        if hasattr(self, "_server_cm"):
            await self._server_cm.__aexit__(None, None, None)
            self.process = None

class CandidateAgent(EloAgent):
    def __init__(self, agent_id: str, worktree_dir: str, model: str = "gemini-3-flash", 
                 provider: str = "opencode", traces_dir: str = "/tmp", orchestrator: Any = None):
        super().__init__(agent_id, worktree_dir, AgentType.CANDIDATE, model, provider, traces_dir, orchestrator)

    def _get_system_prompt(self) -> str:
        return f"""You are a Candidate Agent ({self.agent_id}). 
Your goal is to modify the files in your workspace (e.g., `./`) to solve the given problem and fix any failing tests.

### The ELO Tournament System:
- **Asynchronous & Continuous:** This is a live, ongoing tournament. There are no fixed "rounds."
- **Glicko-2 Ratings:** Your "skill" (code quality) is estimated using the Glicko-2 rating system. Passing tests increases your rating; failing them decreases it.
- **Versioning:** Every time you submit an update, a new **Version** is created. Your rating is inherited from the previous version, but uncertainty (RD) is reset to allow for rapid movement.
- **Reactive Execution:** When you submit, the system automatically runs ALL available tests against your new code.
- **Notifications:** You will be "interrupted" (your current task aborted and restarted) when:
    1. A rival candidate submits an update (so you can analyze their progress).
    2. Your current submission fails a test (so you can fix the bug).

### Submission Process:
1. Modify your code using tools (e.g., `write_file`).
2. Once your changes are ready, send the `update_candidate` action.
The system will automatically compute the diff between your current workspace and the original codebase to create a versioned submission.

CRITICAL: You must output your final decision as a JSON object in your FINAL TEXT RESPONSE. 
DO NOT use tools like 'echo' to output this JSON. It MUST be in your direct text reply to the user.
Format:
{{
  "action": "update_candidate",
  "message": "Summary of changes made."
}}"""

    async def _handle_action(self, action: str, data: Dict[str, Any]) -> str:
        if action == AgentActionType.UPDATE_CANDIDATE.value:
            message = data.get('message', 'No summary provided')
            logging.info(f"Agent {self.agent_id} submitted candidate update: {message}")
            if self.orchestrator:
                await self.orchestrator.submit_update(self.agent_id, message)
            self._transition(AgentState.WAITING)
            # Waiting for next event (interrupt)
            await asyncio.sleep(60)
            return "Update submitted. Awaiting next event."
        raise LLMResponseError(f"Invalid action '{action}' for CandidateAgent.")

class TesterAgent(EloAgent):
    def __init__(self, agent_id: str, worktree_dir: str, model: str = "gemini-3-flash", 
                 provider: str = "opencode", traces_dir: str = "/tmp", orchestrator: Any = None):
        super().__init__(agent_id, worktree_dir, AgentType.TESTER, model, provider, traces_dir, orchestrator)

    def _get_system_prompt(self) -> str:
        return f"""You are a Testing Agent ({self.agent_id}).
Your goal is to write a script that verifies if a codebase correctly solves the problem or exposes a specific bug.

### Your Role:
You are NOT a rival to the candidates. You are a **Verifier**. Your goal is to produce high-quality tests that can distinguish between a correct solution and a buggy one. Your tests also have an ELO rating based on their "authority" and discriminative power.

### The ELO Tournament System:
- **Asynchronous:** This is an ongoing tournament. You can submit tests at any time.
- **Reactive:** Whenever you submit a new test, it is automatically executed against the latest version of ALL current candidates.
- **The Overlay Mechanism:**
    1. You write your test files (e.g., `test.sh`, `tests/v1.py`) in your own workspace (e.g., `./`).
    2. When you submit your action, the system bundles ALL your workspace changes (your diff) into a "Test Package".
    3. To execute your test against a candidate: 
       - The system creates a clean copy of the candidate's worktree.
       - Your "Test Package" is **overlaid** (dropped) into the root of their project.
       - Your `entrypoint` command is then executed.

### Submission Process:
1. Create your test files in your workspace.
2. Once ready, send the `propose_test` action specifying the command to run your test.
Your `entrypoint` should exit 0 on success, non-zero on failure.

CRITICAL: You must output your final decision as a JSON object in your FINAL TEXT RESPONSE. 
DO NOT use tools like 'echo' to output this JSON. It MUST be in your direct text reply to the user.
Format:
{{
  "action": "propose_test",
  "entrypoint": "bash test.sh" // Command to run your test from the project root
}}"""

    async def _handle_action(self, action: str, data: Dict[str, Any]) -> str:
        if action == AgentActionType.PROPOSE_TEST.value:
            entrypoint = data.get("entrypoint")
            logging.info(f"Agent {self.agent_id} proposed test: {entrypoint}")
            if self.orchestrator:
                vid = f"test_{self.agent_id}_{int(time.time())}"
                # Get current workspace diff as patch
                patch_content = self.orchestrator.workspace_mgr.get_diff(self.worktree_dir)
                asyncio.create_task(self.orchestrator.add_verifier(vid, patch_content, entrypoint))
            return "Test proposed. You may propose more or wait."
        raise LLMResponseError(f"Invalid action '{action}' for TesterAgent.")

# Deprecated alias for backward compatibility
def AgentSession(agent_id: str, worktree_dir: str, agent_type: Union[str, AgentType] = "candidate", **kwargs):
    if isinstance(agent_type, str):
        agent_type = AgentType(agent_type)
    if agent_type == AgentType.CANDIDATE:
        return CandidateAgent(agent_id, worktree_dir, **kwargs)
    elif agent_type == AgentType.TESTER:
        return TesterAgent(agent_id, worktree_dir, **kwargs)
    else:
        raise ValueError(f"Unknown agent type: {agent_type}")
