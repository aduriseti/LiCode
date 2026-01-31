from dataclasses import dataclass, field
from typing import Dict, Optional, List, Protocol, Tuple, Any
import random
import abc
import json
import logging
import os

import opencode_ai
from opencode_ai import AsyncOpencode
from opencode_ai.types import AssistantMessage
# Note: Part import might vary based on SDK version, assuming standard structure
# from opencode_ai.types.session_chat_params import Part 

logger = logging.getLogger(__name__)

@dataclass
class Move:
    proposed_verifier_content: Optional[str] = None
    updated_code_content: Optional[str] = None
    belief_vector: Dict[str, float] = field(default_factory=dict)
    inference_cost: float = 0.0

class Agent(abc.ABC):
    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    @abc.abstractmethod
    async def get_next_move(self, market_snapshot: dict) -> Move:
        pass

# --- Interface for the Session ---

class OpenCodeSession(Protocol):
    async def send_prompt(self, prompt: str) -> Tuple[str, float]:
        """
        Sends a prompt and returns (response_text, cost).
        """
        ...

# --- Real Implementation using opencode-ai ---

class RealOpenCodeSession:
    def __init__(self, client: AsyncOpencode, session_id: str, model_id: str = "gpt-4o"):
        self.client = client
        self.session_id = session_id
        self.model_id = model_id

    async def send_prompt(self, prompt: str) -> Tuple[str, float]:
        # API signature: chat(..., parts=[...])
        response = await self.client.session.chat(
            id=self.session_id,
            model_id=self.model_id,
            provider_id="openai", # Defaulting to openai for this example
            parts=[{"type": "text", "text": prompt}] # Generic dict structure usually supported
        )
        
        cost = getattr(response, 'cost', 0.0)
        
        text_response = "{}" # Default to empty JSON
        if hasattr(response, 'summary') and isinstance(response.summary, str):
             text_response = response.summary
        
        return text_response, cost

class LLMAgent(Agent):
    def __init__(self, agent_id: str, session: OpenCodeSession):
        super().__init__(agent_id)
        self.session = session

    def _construct_system_prompt(self, snapshot: dict) -> str:
        my_wealth = snapshot.get("wealth", {}).get(self.agent_id, 0.0)
        prices = snapshot.get("sentences", {})
        price_str = "\n".join([f"- {sid}: ${p:.2f}" for sid, p in prices.items()])
        
        prompt = f"""
MARKET UPDATE (Identity: {self.agent_id})
Your Wealth: ${my_wealth:.2f}
Active Market Prices:
{price_str}
OBJECTIVE: Respond with valid JSON only: {{ "proposed_verifier": ..., "updated_code": ..., "beliefs": ... }}
"""
        return prompt

    async def get_next_move(self, market_snapshot: dict) -> Move:
        prompt = self._construct_system_prompt(market_snapshot)
        try:
            response_text, cost = await self.session.send_prompt(prompt)
            
            # Clean up markdown
            cleaned = response_text.strip()
            if cleaned.startswith("```json"): cleaned = cleaned[7:]
            if cleaned.endswith("```"): cleaned = cleaned[:-3]
            
            data = json.loads(cleaned)
            return Move(
                proposed_verifier_content=data.get("proposed_verifier"),
                updated_code_content=data.get("updated_code"),
                belief_vector=data.get("beliefs", {}),
                inference_cost=cost
            )
        except Exception as e:
            logger.error(f"Agent {self.agent_id} error: {e}")
            return Move(inference_cost=0.0)

# --- Mock Implementation for Testing ---

class MockOpenCodeSession:
    def __init__(self, canned_response: Dict[str, Any], cost: float = 0.05):
        self.canned_response = canned_response
        self.cost = cost
        self.last_prompt = ""

    async def send_prompt(self, prompt: str) -> Tuple[str, float]:
        self.last_prompt = prompt
        return json.dumps(self.canned_response), self.cost

class RandomAgent(Agent):
    async def get_next_move(self, market_snapshot: dict) -> Move:
        move = Move()
        if random.random() < 0.1:
            move.updated_code_content = "def solve(): pass"
        if random.random() < 0.1:
            move.proposed_verifier_content = "assert True"
        
        sentences = market_snapshot.get("sentences", {})
        for s_id in sentences:
            move.belief_vector[s_id] = random.random()
        
        move.inference_cost = 0.01 # Fixed cost for random agent
        return move