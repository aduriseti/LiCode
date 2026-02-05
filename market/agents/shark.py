import json
import logging
import os
import sys
from typing import Dict, Any, Optional
from opencode_ai import AsyncOpencode, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

from ..core.state import MarketState
from ..orchestrator import AgentAction

def log_retry_attempt(retry_state):
    if retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        logging.warning(f"Retrying API call due to: {type(exc).__name__}: {exc}")

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

    def _log_interaction(self, prompt: str, response: Any, error: Optional[str] = None):
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
        return f"""You are Agent {self.agent_id}, a strategic software engineer in a Logical Induction Market.
Goal: Produce the best code solution and profit by predicting which solutions/tests are correct.

**Assets & Mechanics:**
- **Candidates (cand_X):** Full project workspaces cloned from the base repo. You each own one.
- **Verifiers (v_HASH):** Test scripts. Price = Market confidence it is VALID (bug-free and correct).

**Your Turn:**
1. Analyze the 'Market Assets' and 'Your Current Code'.
2. Your candidate `cand_X` is a DIRECTORY containing the entire project.
3. You must create/edit specific files (e.g., `solution.py`) within your workspace.
4. Output a JSON object with:
   - "beliefs": Your predicted probability (0.01 to 0.99) for assets.
   - "proposals": List of actions to perform (PATCH code or create VERIFIER).

**IMPORTANT: Output ONLY the JSON block. Do NOT use tools. Do NOT provide a todo list. Do NOT provide any other text besides the JSON block (and optionally a <thought> tag).**

**Proposal Types:**
Type 1: "PATCH" (Fix your code)
- `file_path`: Relative path to the file you want to edit (e.g., "solution.py"). Defaults to "solution.py" if omitted.
- `old_code`: Exact unique string to find in the file.
- `new_code`: The replacement string.
- OR use `type: "CANDIDATE"` with `code` to overwrite the entire file.

Type 2: "VERIFIER" (Create test)
- `files`: Dictionary mapping filenames to content. MUST include `run.sh`.
- `run.sh`: Executable script acting as the entry point. Exits 0 on pass, non-zero on fail.

**Example Output:**
<thought>My code handles positive numbers but fails on 0. I will fix it and add a test case.</thought>
```json
{{
  "beliefs": {{
    "cand_{self.agent_id.split('_')[-1]}": 0.95,
    "v_existing_test": 0.1
  }},
  "proposals": [
    {{
      "type": "PATCH",
      "file_path": "solution.py",
      "old_code": "return n * n",
      "new_code": "return n * n if n != 0 else 0"
    }},
    {{
      "type": "VERIFIER",
      "files": {{
        "run.sh": "#!/bin/bash\\npython3 test.py",
        "test.py": "import solution\\nimport unittest\\n\\nclass TestSolution(unittest.TestCase):\\n    def test_zero(self):\\n        self.assertEqual(solution.solve(0), 0)\\n\\nif __name__ == '__main__':\\n    unittest.main()"
      }}
    }}
  ]
}}
```
"""

    @retry(
        retry=retry_if_exception_type(APITimeoutError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        reraise=True,
        before_sleep=log_retry_attempt
    )
    async def get_action(self, state: MarketState) -> AgentAction:
        """
        Analyzes the market state and returns an action.
        """
        await self.initialize_session()
        user_prompt = self._format_state_prompt(state)
        
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

        if not content:
            msg = f"Shark {self.agent_id} got empty response. Response object: {response}"
            sys.stderr.write(msg + "\n")
            if hasattr(response, "info") and "error" in response.info:
                raise RuntimeError(f"Shark {self.agent_id} API Error: {response.info['error']}")
            raise RuntimeError(f"Shark {self.agent_id} returned empty content.")
        
        # 3. Parse JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        else:
            # Try to find JSON block manually if no markdown
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                content = content[start:end+1]
            
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            # Try to handle common LLM failure modes:
            # 1. Extra text around the JSON block
            # 2. Multiple objects (e.g. a todo list before the answer)
            import re
            
            # Find all JSON-like objects
            matches = re.findall(r'\{[^{}]*\}', content)
            for m in reversed(matches): # Search from end, usually the answer is at the end
                try:
                    candidate = json.loads(m)
                    if "beliefs" in candidate or "proposals" in candidate:
                        data = candidate
                        break
                except:
                    continue
            else:
                # Try finding the largest block starting with { and ending with }
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        data = json.loads(content[start:end+1])
                    except:
                        raise RuntimeError(f"Shark {self.agent_id} returned invalid JSON: {content}") from e
                else:
                    raise RuntimeError(f"Shark {self.agent_id} returned invalid JSON: {content}") from e
        
        return AgentAction(
            agent_id=self.agent_id,
            beliefs=data.get("beliefs", {}),
            proposals=data.get("proposals", [])
        )

    def _format_state_prompt(self, state: MarketState) -> str:
        # Create a concise summary of the market
        lines = [f"Round: {state.round_num}"]
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
            
        # Show Current Code Context
        cid = f"cand_{self.agent_id.split('_')[-1]}"
        if cid in state.assets:
            asset = state.assets[cid]
            if asset.code_path and os.path.exists(asset.code_path):
                try:
                    # If directory, look for solution.py or list files
                    target_path = asset.code_path
                    if os.path.isdir(target_path):
                        sol_path = os.path.join(target_path, "solution.py")
                        if os.path.exists(sol_path):
                            target_path = sol_path
                        else:
                            # If no solution.py, maybe list the dir?
                            # For now, just say empty or new file
                            target_path = None
                            lines.append(f"\n--- Your Source Code (Directory: {asset.code_path}) ---\n(No solution.py found. Create one!)\n-----------------------------------")

                    if target_path:
                        with open(target_path, "r") as f:
                            code = f.read()
                        lines.append(f"\n--- Your Source Code ({target_path}) ---\n{code}\n-----------------------------------")
                except Exception as e:
                    lines.append(f"\n[Error reading source: {e}]")
            
        lines.append("\nYour Holdings:")
        if self.agent_id in state.agents:
            for aid, qty in state.agents[self.agent_id].shares.items():
                lines.append(f"- {aid}: {qty:.1f} shares")
                
        return "\n".join(lines)
