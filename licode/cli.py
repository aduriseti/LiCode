import asyncio
import sys
import argparse
from licode.orchestrator import Orchestrator

def main():
    parser = argparse.ArgumentParser(description="Run the LiCode Logical Induction Tournament")
    parser.add_argument("prompt", help="The coding task prompt")
    parser.add_argument("--count", type=int, default=3, help="Number of agents")
    parser.add_argument("--budget", type=float, default=1000.0, help="Total budget")
    parser.add_argument("--rounds", type=int, default=5, help="Number of rounds")
    
    args = parser.parse_args()
    
    orchestrator = Orchestrator(
        prompt=args.prompt,
        agent_count=args.count,
        budget=args.budget
    )
    
    try:
        asyncio.run(orchestrator.run_tournament(rounds=args.rounds))
    except KeyboardInterrupt:
        print("Tournament interrupted.")
    finally:
        # Cleanup handled in run_tournament usually, but if crashed:
        # orchestrator.cleanup()
        pass

if __name__ == "__main__":
    main()
