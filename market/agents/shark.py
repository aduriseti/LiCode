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
Your Goal: Win the tournament by producing the code that BEST satisfies the User's Problem Statement and profiting from accurate predictions.
Your assigned candidate solution is "{cid}".

**The Environment:**
- You are operating in a cloned workspace of the user's project.
- You have WRITE access ONLY to your assigned workspace ("{cid}"). You cannot modify other agents' code or the base system.
- The market evaluates "Code Quality" based on which Candidate passes the most "Valid Verifiers" (tests).
- **Verifiers** are test scripts proposed by agents. The market decides if a verifier is "Valid" (correctly tests the requirement) based on trading.

**Your Capabilities:**
1. **Explore:** You can read any file in your workspace (provided in the context).
2. **Modify:** You can PATCH any file or CREATE new files to implement the solution.
3. **Verify:** You can propose new VERIFIERS (tests) to prove your code works or to expose bugs in others.

**Strategy:**
- **Implement:** Write code that solves the user's problem. Do not limit yourself to one file unless restricted by the problem.
- **Test:** Write robust tests (Verifiers) that pass on your code but fail on broken code.
- **Bet:** High confidence (0.9+) means you believe a candidate is good or a test is valid. Low confidence means the opposite.

**Output Format:**
You must output a single JSON object. Do not include markdown formatting like ```json ... ``` outside of the block if possible, but the parser is robust.

{{
  "beliefs": {{
    "cand_X": 0.0-1.0, // Probability that Candidate X is the BEST solution
    "v_HASH": 0.0-1.0  // Probability that Verifier HASH is a VALID test
  }},
  "proposals": [
    // Action 1: Modify Code
    {{
      "type": "PATCH",
      "file_path": "path/to/file.py", // Relative to root
      "old_code": "exact string to replace",
      "new_code": "new string"
    }},
    // OR Full Rewrite
    {{
      "type": "CANDIDATE",
      "file_path": "path/to/new_or_existing_file.py",
      "code": "full content of file"
    }},
    // Action 2: Create Test (Verifier)
    {{
      "type": "VERIFIER",
      "files": {{
        "run.sh": "#!/bin/bash\\npython3 test_feature.py", // Entry point (exit 0 = pass)
        "test_feature.py": "import ..."
      }}
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
        
        # 1. Get list of files to compare (respecting .gitignore)
        try:
            res = subprocess.run(
                ["git", "ls-files", "-co", "--exclude-standard"],
                capture_output=True, text=True, check=True
            )
            project_files = res.stdout.splitlines()
        except Exception as e:
            logging.warning(f"Failed to get project files via git ls-files: {e}")
            project_files = []

        async def get_candidate_diff(aid, asset) -> str:
            if not asset.code_path or not os.path.exists(asset.code_path):
                return f"\n--- {aid} Diff ---\n(Workspace not available)\n------------------"
            
            file_diffs = []
            tasks = []
            import shlex
            
            # For each project file, run an individual diff if it exists in the candidate worktree
            for f in project_files:
                cand_file = os.path.join(asset.code_path, f)
                if os.path.isfile(cand_file):
                    # -c core.filemode=false: Natively ignore permission changes
                    # --no-index: Compare files on disk
                    # sed: Hide the absolute candidate path
                    # head -n 100: Truncate each individual file diff
                    f_q = shlex.quote(f)
                    cand_file_q = shlex.quote(cand_file)
                    cmd = f"git -c core.filemode=false diff --no-index --no-color --src-prefix=a/ --dst-prefix=b/ {f_q} {cand_file_q} | sed 's|{asset.code_path}||g' | head -n 100"
                    
                    async def run_diff(command, filename):
                        process = await asyncio.create_subprocess_shell(
                            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        try:
                            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5)
                            return stdout.decode(errors='replace').strip(), filename
                        except Exception as e:
                            try: process.kill(); await process.wait()
                            except: pass
                            return f"[Error generating diff for {filename}: {e}]", filename

                    tasks.append(run_diff(cmd, f))

            if not tasks:
                return f"\n--- {aid} Diff ---\n(Candidate exactly matches base project - no changes made yet)\n------------------"

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, tuple) and result[0]:
                    file_diffs.append(result[0])
            
            full_diff = "\n".join(file_diffs).strip()
            if full_diff:
                return f"\n--- {aid} Diff ---\n{full_diff}\n------------------"
            else:
                return f"\n--- {aid} Diff ---\n(Candidate exactly matches base project - no changes made yet)\n------------------"

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
