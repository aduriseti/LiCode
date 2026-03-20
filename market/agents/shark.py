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
from ..common.process_registry import registry

class LLMResponseError(Exception):
    """Raised when the LLM returns an invalid or non-JSON response."""
    pass

class FatalAgentError(Exception):
    """Raised for critical agent failures that should stop the tournament."""
    pass

from ..common.agent import BaseAgent, LLMResponseError, FatalAgentError

class Shark(BaseAgent):
    """
    An Inductive Agent (Shark) powered by an LLM via OpenCode API.
    """
    def __init__(self, agent_id: str, model: str = "gemini-3-flash", provider: str = "opencode", 
                 api_url: str = "http://127.0.0.1:4096", 
                 log_path: Optional[str] = None, 
                 timeout: float = 300.0, trace_path: Optional[str] = None,
                 max_retries: int = 3, initial_backoff: float = 120.0, 
                 max_backoff: float = 1000.0):
        super().__init__(
            agent_id=agent_id, model=model, provider=provider, api_url=api_url,
            timeout=timeout, log_path=log_path, trace_path=trace_path,
            max_retries=max_retries, max_backoff=max_backoff
        )
        self.system_prompt = self._build_system_prompt()

    def _log_interaction(self, prompt: str, response: Any, error: Optional[str] = None):
        if not self.log_path: return
        try:
            with open(self.log_path, "a") as f:
                f.write(f"\n--- Round Interaction ---\n")
                f.write(f"PROMPT:\n{prompt}\n")
                if error:
                    f.write(f"ERROR: {error}\n")
                else:
                    f.write(f"RESPONSE CONTENT: {response}\n")
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

    async def get_action(self, state: MarketState) -> AgentAction:
        """
        Analyzes the market state and returns an action.
        Uses a self-correction and retry loop for timeouts and parsing errors.
        """
        try:
            await self.initialize_session(self.system_prompt)
            current_prompt = await self._format_state_prompt(state)
            
            max_total_attempts = self.max_retries + 1
            retry_count = 0
            
            for attempt in range(max_total_attempts + 3):
                try:
                    current_timeout = min(self.timeout * (2 ** retry_count), self.max_backoff)
                    content = await self.chat_robust(current_prompt, system_prompt=self.system_prompt, timeout=current_timeout)
                    
                    data = self.parse_json_action(content, ["beliefs", "proposals"])
                    self._log_interaction(current_prompt, content)
                    
                    return AgentAction(
                        agent_id=self.agent_id,
                        beliefs=data.get("beliefs", {}),
                        proposals=data.get("proposals", []),
                        retry_count=retry_count
                    )
                    
                except (APITimeoutError, APIConnectionError) as e:
                    retry_count += 1
                    if isinstance(e, APITimeoutError): await self.interrupt()
                    if retry_count > self.max_retries:
                        return AgentAction(agent_id=self.agent_id, error=str(e), retry_count=retry_count)

                    next_timeout = min(self.timeout * (2 ** retry_count), self.max_backoff)
                    if isinstance(e, APITimeoutError):
                        current_prompt = f"TIMEOUT: Your previous response took more than {current_timeout}s. You have {next_timeout}s now to provide your JSON format action."
                    else:
                        current_prompt = "CONNECTION ERROR: Transient issue. Please retry your JSON format action."
                    
                except LLMResponseError as e:
                    if attempt >= max_total_attempts + 2:
                        return AgentAction(agent_id=self.agent_id, error=str(e), retry_count=retry_count)
                    current_prompt = f"ERROR: Your previous response was invalid: {str(e)}\nPlease provide your updated JSON format action."
            
            return AgentAction(agent_id=self.agent_id, retry_count=retry_count)
            
        except FatalAgentError:
            raise
        except Exception as e:
            logging.error(f"Shark {self.agent_id} critical failure: {e}")
            raise FatalAgentError(f"Shark {self.agent_id} experienced a critical failure: {e}")

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
                # Note: We do NOT commit, just update the index for the diff
                async with registry.spawn(
                    "git", "add", ".", 
                    cwd=asset.code_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                ) as proc_add:
                    await proc_add.wait()
                
                # Run git diff --cached HEAD
                async with registry.spawn(
                    "git", "diff", "--cached", "HEAD",
                    cwd=asset.code_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                ) as proc_diff:
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
