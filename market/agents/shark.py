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
- **Read Access:** You can read files in ANY candidate's worktree to analyze rival solutions.
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

    @retry(
        retry=retry_if_exception_type((APITimeoutError, LLMResponseError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        reraise=True,
        before_sleep=log_retry_attempt()
    )
    async def get_action(self, state: MarketState) -> AgentAction:
        """
        Analyzes the market state and returns an action.
        """
        await self.initialize_session()
        user_prompt = await self._format_state_prompt(state)
        
        logging.info(f"Shark {self.agent_id} calling API...")
        
        response = await self.client.session.chat(
            id=self.session.id,
            model_id=self.model,
            provider_id=self.provider,
            system=self.system_prompt,
            parts=[{"type": "text", "text": user_prompt}]
        )
        
        # Log the raw interaction for debugging
        self._log_interaction(user_prompt, response)
        
        content = getattr(response, "text", "") or getattr(response, "content", "")
        if not content and hasattr(response, "parts"):
            extracted_parts = []
            for p in response.parts:
                text = p.get("text") if isinstance(p, dict) else getattr(p, "text", None)
                if text: extracted_parts.append(text)
            content = "".join(extracted_parts)

        logging.info(f"Shark {self.agent_id} received {len(content)} chars from API.")

        if not content:
            msg = f"Shark {self.agent_id} got empty response. Response object: {response}"
            sys.stderr.write(msg + "\n")
            if hasattr(response, "info") and "error" in response.info:
                raise LLMResponseError(f"Shark {self.agent_id} API Error: {response.info['error']}")
            raise LLMResponseError(f"Shark {self.agent_id} returned empty content.")
        
        # 3. Parse JSON using chompjs and json_repair for maximum robustness
        try:
            from chompjs import parse_js_objects
            from json_repair import loads as repair_loads
            
            # Find all potential JSON objects
            # parse_js_objects is very good at extracting objects from noisy text
            candidates = list(parse_js_objects(content))
            
            # If no candidates, try repairing the whole string
            if not candidates:
                repaired = repair_loads(content)
                if isinstance(repaired, dict):
                    candidates = [repaired]
            
            # Find the best candidate (usually the last one)
            data = None
            for cand in reversed(candidates):
                if isinstance(cand, dict) and ("beliefs" in cand or "proposals" in cand):
                    data = cand
                    break
            
            if data is None:
                raise LLMResponseError(f"Shark {self.agent_id} response missing required keys. Content: {content}")
                
        except Exception as e:
            if isinstance(e, LLMResponseError):
                raise e
            raise LLMResponseError(f"Shark {self.agent_id} returned invalid JSON: {content}") from e
        
        return AgentAction(
            agent_id=self.agent_id,
            beliefs=data.get("beliefs", {}),
            proposals=data.get("proposals", [])
        )

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
        
        # Group by type
        candidates = []
        verifiers = []
        for aid, asset in state.assets.items():
            price = state.get_asset_price(aid)
            path_info = f"(Path: {asset.code_path})" if asset.code_path else ""
            if asset.test_path: path_info = f"(Path: {asset.test_path})"
            
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

        lines.append("\n=== Candidate Code Changes (Diffs) ===")
        
        async def get_candidate_diff(aid, asset) -> str:
            if not asset.code_path or not os.path.exists(asset.code_path):
                return f"\n--- {aid} Diff ---\n(Workspace not available)\n------------------"
            
            # Efficient Project-Wide Diff using Option A:
            # 1. diff -urN: Recursive, handle new/deleted files
            # 2. sed logic: 
            #    - When we see 'diff -urN', reset counter
            #    - If counter < 100, print line and increment
            #    - If counter == 100, print '[Truncated]' and stop printing for this file
            # 3. Exclude noisy paths
            
            exclude_args = []
            for pattern in [".git", ".arenas", "__pycache__", "node_modules", ".home", "*.log", "*.db", ".pytest_cache"]:
                exclude_args.extend(["--exclude", pattern])

            cmd = [
                "diff", "-urN"
            ] + exclude_args + [
                ".", asset.code_path
            ]
            
            # The sed script tracks state to truncate per-file
            # /^diff / matches the start of a new file's diff
            sed_script = '/^diff / { x; s/.*/0/; x; }; x; /^[0-9][0-9]*$/ { s/^99$/100/; t trunc; s/$/1/; x; p; d; :trunc; s/.*/truncated/; i\\... [File Truncated at 100 lines] ...\n; d; }; x; d'
            # Simpler approach: use python to handle the stream if sed is too cryptic
            
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # We'll parse the output in Python to ensure per-file truncation is correct
                stdout_lines = []
                count = 0
                while True:
                    line_bytes = await process.stdout.readline()
                    if not line_bytes: break
                    line = line_bytes.decode(errors='replace')
                    
                    if line.startswith("diff -urN"):
                        count = 0
                        stdout_lines.append(line)
                    elif count < 100:
                        stdout_lines.append(line)
                        count += 1
                        if count == 100:
                            stdout_lines.append("... [File Truncated at 100 lines] ...\n")
                
                await process.wait()
                diff_text = "".join(stdout_lines).strip()
                
                if diff_text:
                    # Cleanup: Remove absolute paths from headers to keep it clean for LLM
                    diff_text = diff_text.replace(asset.code_path, "")
                    return f"\n--- {aid} Diff ---\n{diff_text}\n------------------"
                else:
                    return f"\n--- {aid} Diff ---\n(Candidate exactly matches base project - no changes made yet)\n------------------"
            except Exception as e:
                return f"\n--- {aid} Diff ---\n[Error generating diff: {e}]\n------------------"

        if state.assets:
            diff_results = await asyncio.gather(*[
                get_candidate_diff(aid, asset) 
                for aid, asset in state.assets.items() 
                if asset.type == "CANDIDATE"
            ])
            lines.extend(diff_results)

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
