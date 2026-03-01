import json
import logging
import os
import sys
import subprocess
import asyncio
from typing import Dict, Any, Optional
from opencode_ai import AsyncOpencode, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

from ..core.state import MarketState
from ..orchestrator import AgentAction

class log_retry_attempt:
    def __call__(self, retry_state):
        if retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
            logging.warning(f"Retrying API call due to: {type(exc).__name__}: {exc}")

class LLMResponseError(Exception):
    """Raised when the LLM returns an invalid or non-JSON response."""
    pass

class Shark:
    """
    An Inductive Agent (Shark) powered by an LLM via OpenCode API.
    """
    def __init__(self, agent_id: str, model: str = "gemini-3-flash", provider: str = "opencode", api_url: str = "http://127.0.0.1:4096", log_path: Optional[str] = None, timeout: float = 300.0):
        self.agent_id = agent_id
        self.model = model
        self.provider = provider
        self.log_path = log_path
        # Initialize Async OpenCode client
        # Disable internal retries so Tenacity handles it with logging
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

    async def get_action(self, state: MarketState) -> AgentAction:
        """
        Analyzes the market state and returns an action.
        Uses a self-correction loop for parsing errors.
        """
        await self.initialize_session()
        
        # 1. Generate full state prompt ONCE
        current_prompt = await self._format_state_prompt(state)
        
        # 2. Self-correction loop
        for attempt in range(3): # Up to 3 attempts at correction
            try:
                # Call API with retry only for transient network/timeout errors
                content = await self._chat_with_network_retry(current_prompt)
                
                # 3. Parse and return if successful
                return self._parse_action_response(content)
                
            except LLMResponseError as e:
                if attempt == 2: # Last attempt failed
                    logging.error(f"Shark {self.agent_id} failed after 3 attempts: {e}")
                    # Return empty action as fallback
                    return AgentAction(agent_id=self.agent_id)
                
                # 4. Propagate error to agent for self-correction
                # We send a short error message instead of resending the 10KB state
                logging.warning(f"Shark {self.agent_id} parsing failed. Sending error back for correction (Attempt {attempt+1}/3)")
                current_prompt = f"ERROR: Your previous response was invalid: {str(e)}\nPlease provide your updated beliefs and proposals in the correct JSON format."
        
        return AgentAction(agent_id=self.agent_id) # Final fallback

    @retry(
        retry=retry_if_exception_type(APITimeoutError), # Only retry transient network/hangs
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=20),
        reraise=True,
        before_sleep=log_retry_attempt()
    )
    async def _chat_with_network_retry(self, prompt: str) -> str:
        """Performs the actual API call with transient error handling."""
        logging.info(f"Shark {self.agent_id} calling API...")
        
        if not self.session:
            raise RuntimeError("Session not initialized")

        response = await self.client.session.chat(
            id=self.session.id,
            model_id=self.model,
            provider_id=self.provider,
            system=self.system_prompt,
            parts=[{"type": "text", "text": prompt}]
        )
        
        # Log interaction for debugging
        self._log_interaction(prompt, response)
        
        content = getattr(response, "text", "") or getattr(response, "content", "")
        # Handle cases where response is not as expected
        if not content:
            parts = getattr(response, "parts", [])
            if parts:
                extracted_parts = []
                for p in parts: # type: ignore
                    text = p.get("text") if isinstance(p, dict) else getattr(p, "text", None)
                    if text: extracted_parts.append(text)
                content = "".join(extracted_parts)

        if not content:
            # Empty response is now a Category 1 error (Self-correction)
            info = getattr(response, "info", {})
            if isinstance(info, dict) and "error" in info:
                 raise LLMResponseError(f"API Error Info: {info['error']}")
            raise LLMResponseError("Received empty response content.")
            
        return content

    def _parse_action_response(self, content: str) -> AgentAction:
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
                proposals=data.get("proposals", [])
            )
        except Exception as e:
            if isinstance(e, LLMResponseError):
                raise e
            raise LLMResponseError(f"Invalid JSON format: {str(e)}")

    async def close(self):
        """Gracefully close the API client."""
        await self.client.close()

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

        lines.append("\n=== Test Failures ===")
        if state.test_failures:
            for fail_key, failed in state.test_failures.items():
                if failed:
                    lines.append(f"- {fail_key}")
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
