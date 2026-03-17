import json
import logging
import os
import sys
import subprocess
import asyncio
import threading
from typing import Dict, Any, Optional
from opencode_ai import AsyncOpencode, APITimeoutError, APIConnectionError
from opencode_ai.types import (
    TextPart, 
    ToolPart,
    ToolStateRunning,
    ToolStateCompleted
)
from opencode_ai.types.event_list_response import EventMessagePartUpdated

from ..core.state import MarketState
from ..orchestrator import AgentAction

class LLMResponseError(Exception):
    """Raised when the LLM returns an invalid or non-JSON response."""
    pass

class FatalAgentError(Exception):
    """Raised for critical agent failures that should stop the tournament."""
    pass

class Shark:
    """
    An Inductive Agent (Shark) powered by an LLM via OpenCode API.
    """
    def __init__(self, agent_id: str, model: str = "gemini-3-flash", provider: str = "opencode", 
                 api_url: str = "http://127.0.0.1:4096", 
                 log_path: Optional[str] = None, 
                 timeout: float = 300.0, trace_path: Optional[str] = None,
                 max_retries: int = 3, initial_backoff: float = 120.0, 
                 max_backoff: float = 1000.0):
        self.agent_id = agent_id
        self.model = model
        self.provider = provider
        self.log_path = log_path
        self.trace_path = trace_path
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        # Initialize Async OpenCode client
        self.client = AsyncOpencode(base_url=api_url, timeout=timeout, max_retries=0)
        self.session = None
        self.system_prompt = self._build_system_prompt()

    async def initialize_session(self):
        """Async initialization of the session."""
        if not self.session:
            self.session = await self.client.session.create(extra_body={})
            if not hasattr(self.session, 'id'):
                raise RuntimeError(f"Failed to create session for Shark {self.agent_id}. Got: {self.session}")
            
            if self.log_path:
                with open(self.log_path, "a") as f:
                    f.write(f"=== Session Created: {self.session.id} ===\n")
                    f.write(f"=== SYSTEM PROMPT ===\n{self.system_prompt}\n=====================\n")

    def _log_interaction(self, prompt: str, response: Any, error: Optional[str] = None):
        # Log to file
        if not self.log_path: return
        
        try:
            with open(self.log_path, "a") as f:
                f.write(f"\n--- Round Interaction ---\n")
                f.write(f"PROMPT:\n{prompt}\n")
                if error:
                    f.write(f"ERROR: {error}\n")
                else:
                    f.write(f"RESPONSE OBJECT: {response}\n")
        except Exception as e:
            logging.error(f"Failed to write session log for {self.agent_id}: {e}")

    def _build_system_prompt(self) -> str:
        cid = f"cand_{self.agent_id.split('_')[-1]}"
        return f"""You are Agent {self.agent_id}, a strategic software engineer participating in a Logical Induction Market Tournament.
Your Goal: Win the tournament by producing the project that BEST satisfies the User's Problem Statement and profiting from accurate predictions.
Your assigned candidate solution is the ENTIRE worktree "{cid}".

**Session Management Policy:**
If your session is interrupted due to a timeout, it is likely because the system detected an unproductive loop or excessive tool use.
In such cases, the system will automatically retry with an increased time limit (initial: {self.timeout}s, scaling up to: {self.max_backoff}s).
Your session will be interrupted (equivalent to pressing Escape twice) during timeouts to restore responsiveness.

**The Environment:**
- **Read Access:** You can ONLY read files in your own worktree ("{cid}"). You do NOT have direct read/exec access to rival worktrees; instead, you are provided with **Diff Summaries** of their changes in the Market Assets section below to analyze their solutions.
- **Write Access:** You can ONLY modify your own worktree ("{cid}").
- **Modifications:** You have direct write access. Use your tools (e.g. `write_file`) to edit your code. Do NOT return file content in your JSON response.

**The Market & Verification:**
- **Verifiers:** You propose tests (`VERIFIER` packages) to prove your code works or expose bugs in others.
- **Creation:** To propose a Verifier:
    1. Create a directory in your worktree (e.g., `tests/v1`).
    2. Write your test files (must include `run.sh`) into that directory.
    3. Return a `VERIFIER` proposal in your JSON pointing to that path.
- **Execution:** The system will copy that directory to the central registry and run it against all candidates.
    1. The system creates a clean sandbox.
    2. It copies the target Candidate's *entire worktree* into the sandbox.
    3. It overlays your Verifier files (e.g. `run.sh`) into the root.
    4. It executes `./run.sh`.
    **Implication:** Your `run.sh` executes **inside** a copy of the candidate's project. You can access their `main.py` directly as `./main.py`.
- **Scope:** Verifiers can test Logic, Performance, and Stability.
- **Self-Verification:** Your verifier MUST pass on your own candidate! If it fails, you look incompetent.

**Critical Rule: The Consensus Interface**
- **The Contract:** You must implement the interface defined or implied by the Problem Statement (e.g., "script must be named `main.py`", "server must listen on port 3000").
- **Portability:** Your Verifier MUST NOT import internal code from your own solution (e.g., `from my_utils import func`). It must test the **Observable Behavior** of the project (e.g., running the CLI, making HTTP requests, checking output files).
- **Good vs Bad Failures:**
    - **GOOD:** Your test fails on Rival B because their logic is wrong.
    - **BAD:** Your test fails on Rival B because you hardcoded `import agent_0_utils` which they don't have.

**Output Format:**
You must output a single JSON object.

{{
  "beliefs": {{
    "cand_X": 0.0-1.0, // Probability that Candidate X is the BEST solution
    "v_HASH": 0.0-1.0  // Probability that Verifier HASH is a VALID test of the contract
  }},
  "proposals": [
    // Register a Verifier you have already written to your disk
    {{
      "type": "VERIFIER",
      "path": "tests/my_new_test" // Relative path to directory containing run.sh
    }}
  ]
}}
"""

    def _append_to_trace(self, content: str):
        """Helper for thread-safe file appending."""
        if not self.trace_path:
            return
        try:
            os.makedirs(os.path.dirname(self.trace_path), exist_ok=True)
            with open(self.trace_path, "a") as f:
                f.write(content)
                f.flush()
        except Exception:
            pass

    async def get_action(self, state: MarketState) -> AgentAction:
        """
        Analyzes the market state and returns an action.
        Uses a self-correction and retry loop for timeouts and parsing errors.
        """
        try:
            await self.initialize_session()
            
            # 1. Generate full state prompt ONCE
            current_prompt = await self._format_state_prompt(state)
            
            # 2. Unified Retry and Correction loop
            # max_total_attempts = 1 (initial) + max_retries
            max_total_attempts = self.max_retries + 1
            retry_count = 0
            
            # We use a loop that can handle both network retries and parsing corrections
            # Total loop iterations is slightly higher than max_retries to allow for a few JSON fixes
            for attempt in range(max_total_attempts + 3):
                try:
                    # Calculate timeout for this attempt: doubles every retry
                    current_timeout = min(self.timeout * (2 ** retry_count), self.max_backoff)
                    
                    # Call API
                    content = await self._chat_with_network_retry(current_prompt, timeout=current_timeout)
                    
                    # 3. Parse and return if successful
                    return self._parse_action_response(content, retry_count=retry_count)
                    
                except (APITimeoutError, APIConnectionError) as e:
                    retry_count += 1
                    
                    if isinstance(e, APITimeoutError):
                        await self.interrupt()

                    if retry_count > self.max_retries:
                        logging.error(f"Shark {self.agent_id} network/timeout failed after {self.max_retries} retries: {e}. Falling back to empty action.")
                        return AgentAction(agent_id=self.agent_id, error=str(e), retry_count=retry_count)

                    # Calculate timeout for the NEXT attempt
                    next_timeout = min(self.timeout * (2 ** retry_count), self.max_backoff)
                    
                    if isinstance(e, APITimeoutError):
                        logging.warning(f"Shark {self.agent_id} timed out ({current_timeout}s). Interrupting and retrying immediately with {next_timeout}s limit (Retry {retry_count}/{self.max_retries})")
                        current_prompt = f"TIMEOUT: Your previous response took more than {current_timeout}s and was interrupted to break an unproductive loop. You have {next_timeout}s for this attempt to provide your updated beliefs and proposals in the correct JSON format now."
                    else:
                        logging.warning(f"Shark {self.agent_id} connection error: {e}. Retrying immediately (Retry {retry_count}/{self.max_retries})")
                        current_prompt = "CONNECTION ERROR: There was a transient network issue. Please provide your updated beliefs and proposals in the correct JSON format now."
                    
                    # No sleep here - immediate retry as requested
                    
                except LLMResponseError as e:
                    # Self-correction attempt (doesn't count towards network retries)
                    if attempt >= max_total_attempts + 2:
                        logging.error(f"Shark {self.agent_id} failed parsing after multiple correction attempts: {e}. Falling back to empty action.")
                        return AgentAction(agent_id=self.agent_id, error=str(e), retry_count=retry_count)

                    logging.warning(f"Shark {self.agent_id} parsing failed. Sending error back for correction (Attempt {attempt+1})")
                    current_prompt = f"ERROR: Your previous response was invalid: {str(e)}\nPlease provide your updated beliefs and proposals in the correct JSON format."
            
            return AgentAction(agent_id=self.agent_id, retry_count=retry_count)
            
        except FatalAgentError:
            raise
        except Exception as e:
            logging.error(f"Shark {self.agent_id} critical failure: {e}")
            raise FatalAgentError(f"Shark {self.agent_id} experienced a critical failure: {e}")

    async def _chat_with_network_retry(self, prompt: str, timeout: Optional[float] = None) -> str:
        """Sends a message to the OpenCode session with trace capture."""
        logging.info(f"Shark {self.agent_id} calling API...")
        if not self.session:
            await self.initialize_session()
            
        # Use provided timeout or default
        call_timeout = timeout or self.timeout
        
        # Log prompt to trace
        if self.trace_path:
            await asyncio.to_thread(self._append_to_trace, f"\n\n[PROMPT]\n{prompt}\n\n[ASSISTANT]\n")

        # Track part states for trace logging
        part_lengths = {}
        seen_tool_parts = set()

        try:
            # 1. Start event stream for tracing
            # We use the existing self.client for both to avoid extra overhead
            # and potential connection pool issues.
            stream = await self.client.event.list()
            
            # 2. Start chat in parallel
            # We use self.client.session.chat directly
            chat_task = asyncio.create_task(self.client.session.chat(
                id=self.session.id,
                model_id=self.model,
                provider_id=self.provider,
                system=self.system_prompt,
                parts=[{"type": "text", "text": prompt}],
                timeout=call_timeout
            ))
            
            # 3. Consume stream for tracing in a separate task
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
                                            await asyncio.to_thread(self._append_to_trace, f"\n[TOOL RESULT: {state.output}]\n")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logging.debug(f"Trace stream consumer error: {e}")

            consumer_task = asyncio.create_task(consume_stream())
            
            try:
                # 4. Wait for chat to finish
                # If this fails with a JSON error, it means the server returned an empty or malformed body
                chat_response = await chat_task
                
                # Give the stream consumer a moment to process any final events
                await asyncio.sleep(0.5)
            finally:
                consumer_task.cancel()
                try:
                    await consumer_task
                except asyncio.CancelledError:
                    pass
                await stream.close()

            # 5. Extract text from the chat response
            # Using the response object directly is more robust than re-fetching messages
            extracted_text = []
            if chat_response and hasattr(chat_response, "parts"):
                for part in chat_response.parts:
                    if isinstance(part, TextPart):
                        extracted_text.append(part.text)
            
            content = "".join(extracted_text)
            
            # Fallback: if chat_response failed to provide text, try fetching messages as a last resort
            if not content:
                logging.warning(f"Shark {self.agent_id} chat response had no text. Attempting message list fallback...")
                messages = await self.client.session.messages(id=self.session.id)
                if messages:
                    last_msg_item = messages[-1]
                    for part in last_msg_item.parts:
                        if isinstance(part, TextPart):
                            extracted_text.append(part.text)
                    content = "".join(extracted_text)
            
            self._log_interaction(prompt, content)
            
            if not content:
                # If we still have no content, it might be that the model just returned an empty string 
                # (e.g. if it only called tools and then stopped).
                # We check for tool calls in the response.
                has_tools = any(isinstance(part, ToolPart) for part in getattr(chat_response, "parts", []))
                if has_tools:
                    logging.warning(f"Shark {self.agent_id} returned tool calls but no final text. This might happen if the model is in a tool-use loop.")
                    # Return a placeholder to allow the tournament to continue (it will likely retry or fix itself in next step)
                    return "{}"
                
                raise FatalAgentError(f"Received empty response content from Shark {self.agent_id}.")

            return content

        except (FatalAgentError, APITimeoutError, APIConnectionError):
            raise
        except Exception as e:
            # Check if this is an API/JSON error that should be retried (e.g. auth failure or 503 returning HTML)
            err_str = str(e)
            if "Expecting value" in err_str or "JSONDecodeError" in type(e).__name__:
                logging.warning(f"Shark {self.agent_id} received malformed JSON (likely auth error or transient failure). Treating as connection error to trigger retry: {e}")
                raise APIConnectionError(request=None)

            # Log the full exception for diagnosis
            logging.error(f"API call or processing failed for {self.agent_id}: {str(e)}")
            raise FatalAgentError(f"API call or processing failed for {self.agent_id}: {e}")


    def _parse_action_response(self, content: str, retry_count: int = 0) -> AgentAction:
        """Helper to parse JSON from LLM content."""
        logging.info(f"Shark {self.agent_id} received {len(content)} chars from API.")
        
        try:
            from chompjs import parse_js_objects
            from json_repair import loads as repair_loads
            
            candidates = list(parse_js_objects(content))
            if not candidates:
                repaired = repair_loads(content)
                if isinstance(repaired, dict):
                    candidates = [repaired]
            
            data = None
            for cand in reversed(candidates):
                if isinstance(cand, dict) and ("beliefs" in cand or "proposals" in cand):
                    data = cand
                    break
            
            if data is None:
                raise LLMResponseError(f"Response missing 'beliefs' or 'proposals' keys. Content sample: {content[:100]}...")
                
            return AgentAction(
                agent_id=self.agent_id,
                beliefs=data.get("beliefs", {}),
                proposals=data.get("proposals", []),
                retry_count=retry_count
            )
        except Exception as e:
            if isinstance(e, LLMResponseError):
                raise e
            raise LLMResponseError(f"Invalid JSON format: {str(e)}")

    async def close(self):
        """Gracefully close the API client."""
        await self.client.close()

    async def interrupt(self):
        """Interrupts the current session (equivalent to pressing Escape twice)."""
        try:
            if self.session and hasattr(self.session, "id"):
                await self.client.session.abort(id=self.session.id)
                logging.info(f"Interrupted session for Shark {self.agent_id}")
        except Exception as e:
            logging.debug(f"Failed to interrupt session for {self.agent_id}: {e}")

    async def shutdown(self):
        """Cleanly closes the agent resources."""
        await self.interrupt()
        await self.close()

    async def _format_state_prompt(self, state: MarketState) -> str:
        # Create a concise summary of the market
        lines = [f"You are Agent: {self.agent_id}", f"Round: {state.round_num}"]
        if state.prompt:
            lines.append(f"\nPROBLEM STATEMENT:\n{state.prompt}\n")

        if self.agent_id in state.agents:
            lines.append(f"Your Wealth: {state.agents[self.agent_id].wealth}")
        else:
            lines.append("Your Wealth: 0")
            
        lines.append("\n=== Market Assets ===")
        
        # Determine current agent's candidate ID
        my_cid = f"cand_{self.agent_id.split('_')[-1]}"

        # Group by type
        candidates = []
        verifiers = []
        for aid, asset in state.assets.items():
            price = state.get_asset_price(aid)
            
            # Privacy: Mask paths. Only tell them their OWN path as "./"
            if aid == my_cid:
                path_info = "(Your Workspace: use './' to access files)"
            else:
                path_info = "" # Hide paths for rivals
            
            if asset.test_path and asset.type == "VERIFIER":
                # Verifiers are public by design, but we still mask path
                path_info = "(Verifier Registry)"
            
            line = f"- {aid}: {price:.3f} {path_info} ({asset.description})"
            if asset.type == "CANDIDATE":
                # Check for verifier failures
                failures = [v_id for key, failed in state.test_failures.items() if failed and key.endswith(f":{aid}") for v_id in [key.split(":")[0]]]
                if failures:
                    line += f" [FAILED TESTS: {', '.join(failures)}]"
                candidates.append(line)
            else:
                verifiers.append(line)
                
        lines.append("\n-- Candidates (Price = Probability this is the BEST solution) --")
        if candidates:
            lines.extend(candidates)
        else:
            lines.append("(None)")
            
        lines.append("\n-- Verifiers (Price = Probability this test is VALID) --")
        if verifiers:
            lines.extend(verifiers)
        else:
            lines.append("(None)")

        lines.append("\n=== Candidate Code Changes (Diffs) ===")
        
        async def get_candidate_diff(aid, asset) -> str:
            if not asset.code_path or not os.path.isdir(asset.code_path):
                return f"--- {aid} Diff ---\n(Workspace not available)"
            
            try:
                # Use Shadow Git: Stage changes -> Diff against Baseline
                # We need to stage current changes first to capture them
                # Note: We do NOT commit, just update the index for the diff
                proc_add = await asyncio.create_subprocess_shell(
                    "git add .", 
                    cwd=asset.code_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await proc_add.wait()
                
                # Run git diff --cached HEAD
                proc_diff = await asyncio.create_subprocess_exec(
                    "git", "diff", "--cached", "HEAD",
                    cwd=asset.code_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc_diff.communicate()
                
                if proc_diff.returncode != 0:
                    return f"--- {aid} Diff ---\n(Error generating diff: {stderr.decode()})"
                
                full_diff = stdout.decode(errors='replace')
                if not full_diff.strip():
                     return f"--- {aid} Diff ---\n(No changes from baseline)"

                # Process Diff with Truncation
                processed_diff = []
                current_file_diff = []
                
                for line in full_diff.splitlines():
                    if line.startswith("diff --git"):
                        # Process previous file
                        if current_file_diff:
                            if len(current_file_diff) > 100:
                                processed_diff.extend(current_file_diff[:100])
                                processed_diff.append(f"... (Truncated {len(current_file_diff) - 100} lines) ...")
                            else:
                                processed_diff.extend(current_file_diff)
                        current_file_diff = [line]
                    else:
                        current_file_diff.append(line)
                        
                # Process last file
                if current_file_diff:
                    if len(current_file_diff) > 100:
                        processed_diff.extend(current_file_diff[:100])
                        processed_diff.append(f"... (Truncated {len(current_file_diff) - 100} lines) ...")
                    else:
                        processed_diff.extend(current_file_diff)

                final_output = "\n".join(processed_diff)
                return f"--- {aid} Diff ---\n{final_output}\n"

            except Exception as e:
                return f"--- {aid} Diff ---\n[Error: {e}]"

        candidates_diffs = []
        if state.assets:
             # Run in parallel
            tasks = []
            for aid, asset in state.assets.items():
                if asset.type == "CANDIDATE":
                    tasks.append(get_candidate_diff(aid, asset))
            
            if tasks:
                candidates_diffs = await asyncio.gather(*tasks)

        lines.extend(candidates_diffs)


        lines.append("\n=== Verifier Code ===")
        for aid, asset in state.assets.items():
             if asset.type == "VERIFIER" and asset.test_path:
                try:
                    # List files in verifier dir
                    files = [f for f in os.listdir(asset.test_path) if f.endswith(('.py', '.sh'))]
                    content = ""
                    for fname in sorted(files)[:2]: # Show first 2 relevant files
                        fpath = os.path.join(asset.test_path, fname)
                        if os.path.isfile(fpath):
                             with open(fpath, "r", errors='replace') as f:
                                c = f.read(1000)
                                if f.read(1): c += "\n...(truncated)"
                             content += f"File: {fname}\n{c}\n"
                    
                    if content:
                         lines.append(f"\n--- {aid} Content ---\n{content}\n---------------------")
                except Exception as e:
                    lines.append(f"\n[Error reading verifier {aid}: {e}]")
            
        lines.append("\nYour Holdings:")
        if self.agent_id in state.agents:
            for aid, qty in state.agents[self.agent_id].shares.items():
                lines.append(f"- {aid}: {qty:.1f} shares")
                
        return "\n".join(lines)
