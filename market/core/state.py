from dataclasses import dataclass, field, asdict
from typing import Dict, List, Literal, Optional
import json

AssetType = Literal["VERIFIER", "CANDIDATE"]

@dataclass
class MarketAsset:
    id: str
    type: AssetType
    description: str
    q_yes: float = 0.0
    q_no: float = 0.0
    
    # Metadata for candidates
    code_path: Optional[str] = None
    
    # Metadata for verifiers
    test_path: Optional[str] = None
    
    def to_dict(self):
        return asdict(self)
    
    @staticmethod
    def from_dict(data):
        return MarketAsset(**data)

@dataclass
class AgentPortfolio:
    agent_id: str
    wealth: float
    # asset_id -> shares (positive for YES, negative for NO/short)
    # Note: In our LMSR logic, owning -10 shares is "Shorting". 
    # But strictly speaking, LMSR usually tracks YES and NO shares separately.
    # To simplify, we'll track "net_yes_shares". 
    # If > 0, holding YES. If < 0, holding NO (effectively).
    # Wait, strict LMSR separates them. Let's track both if needed, 
    # but usually "Short YES" = "Buy NO".
    # Let's stick to the convention: positive = YES shares, negative = NO shares.
    shares: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self):
        return asdict(self)
    
    @staticmethod
    def from_dict(data):
        return AgentPortfolio(**data)

@dataclass
class MarketBond:
    agent_id: str
    asset_id: str
    q_shares: float
    unlock_round: int

    def to_dict(self):
        return asdict(self)

@dataclass
class MarketState:
    round_num: int
    liquidity_b: float
    prompt: str = ""
    assets: Dict[str, MarketAsset] = field(default_factory=dict)
    agents: Dict[str, AgentPortfolio] = field(default_factory=dict)
    whale_wealth: float = 0.0
    whale_shares: Dict[str, float] = field(default_factory=dict) # Track Whale inventory
    bonds: List[MarketBond] = field(default_factory=list)
    
    # Track which tests failed which candidates
    # (verifier_id, candidate_id) -> bool (True = failed)
    test_failures: Dict[str, bool] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "round_num": self.round_num,
            "liquidity_b": self.liquidity_b,
            "prompt": self.prompt,
            "whale_wealth": self.whale_wealth,
            "whale_shares": self.whale_shares,
            "assets": {k: v.to_dict() for k, v in self.assets.items()},
            "agents": {k: v.to_dict() for k, v in self.agents.items()},
            "test_failures": self.test_failures,
            "bonds": [b.to_dict() for b in self.bonds]
        }, indent=2)

    def clone(self):
        """Returns a deep copy of the current state."""
        return MarketState.from_json(self.to_json())

    def get_prices(self) -> Dict[str, float]:
        """Returns a dictionary of all current asset prices."""
        return {aid: self.get_asset_price(aid) for aid in self.assets}

    @staticmethod
    def from_json(json_str: str):
        data = json.loads(json_str)
        state = MarketState(
            round_num=data["round_num"],
            liquidity_b=data["liquidity_b"],
            prompt=data.get("prompt", ""),
            whale_wealth=data["whale_wealth"],
            whale_shares=data.get("whale_shares", {}),
            test_failures=data.get("test_failures", {})
        )
        
        for k, v in data["assets"].items():
            state.assets[k] = MarketAsset.from_dict(v)
            
        for k, v in data["agents"].items():
            state.agents[k] = AgentPortfolio.from_dict(v)
            
        if "bonds" in data:
            state.bonds = [MarketBond(**b) for b in data["bonds"]]
            
        return state

    def get_asset_price(self, asset_id: str) -> float:
        """Helper to get price using current liquidity"""
        from .lmsr import LMSRMarket
        asset = self.assets.get(asset_id)
        if not asset:
            return 0.5
        return LMSRMarket.current_price(asset.q_yes, asset.q_no, self.liquidity_b)
