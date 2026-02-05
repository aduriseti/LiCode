import argparse
import json
import sys
from market.orchestrator import Orchestrator, AgentAction
from market.core.state import MarketState

def main():
    parser = argparse.ArgumentParser(description="Logical Induction Market CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # INIT
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--prompt", type=str, required=True)
    init_parser.add_argument("--agents", type=int, default=3)
    init_parser.add_argument("--budget", type=float, default=1000.0)
    
    # STEP
    step_parser = subparsers.add_parser("step")
    step_parser.add_argument("--state", type=str, required=True, help="Path to market_state.json")
    step_parser.add_argument("--actions", type=str, required=True, help="Path to actions.json")
    
    args = parser.parse_args()
    
    if args.command == "init":
        orch = Orchestrator(args.prompt, args.agents, args.budget)
        print(orch.state.to_json())
        
    elif args.command == "step":
        # Load State
        with open(args.state, 'r') as f:
            state_json = f.read()
        state = MarketState.from_json(state_json)
        
        # Load Actions
        with open(args.actions, 'r') as f:
            actions_data = json.load(f)
            
        actions = []
        for a in actions_data:
            actions.append(AgentAction(
                agent_id=a["agent_id"],
                beliefs=a.get("beliefs", {}),
                proposals=a.get("proposals", [])
            ))
            
        # Run Round
        orch = Orchestrator("", 0, state=state)
        orch.process_round(actions)
        
        # Output pretty summary to stderr for streaming UI
        sys.stderr.write(orch.get_pretty_summary() + "\n")
        
        print(orch.state.to_json())

if __name__ == "__main__":
    main()
