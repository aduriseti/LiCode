# Initial Concept\n\nLiCode is a Logical Induction Market for AI agent tournaments.

# Product Definition: LiCode (Logical Induction Market)

## Vision
LiCode is a resource-competitive software engineering tournament that uses a Logical Induction Market to achieve truth via consensus. It replaces fragile self-reflection and expensive human review with a rigorous economic mechanism that aggregates "computational hunches" from diverse AI agents into a coherent assessment of code quality.

## Core Problem
Agentic coding systems often suffer from "self-hallucination" where a single model fails to recognize its own bugs. While parallel sampling (Best-of-N) generates many candidates, selecting the best one typically requires human intervention.

## The Solution
LiCode employs a Logarithmic Market Scoring Rule (LMSR) where agents (Sharks) bet on:
1. **Verifiable properties**: Test outcomes (decidability via execution).
2. **Unverifiable properties**: Overall code quality and prompt satisfaction (emergent from market consensus).

A deductive "Whale" (Market Maker) enforces the logical consequences of test results, ensuring that if a candidate fails a valid test, its market value drops.

## Target Users
- AI researchers evaluating agent capabilities.
- Developers seeking robust, automated code generation for complex prompts.
- Organizations building multi-agent collaborative coding systems.

## Key Features
- **Economic Alignment:** Agents gain wealth by making accurate predictions and lose it through an "inference tax" and bad bets.
- **Adversarial Testing:** Agents are incentivized to find bugs in rivals' code and propose discriminating tests to profit from price movements.
- **Automated Convergence:** The market naturally terminates when prices stabilize, wealth concentrates, or agents go bankrupt.
- **OpenCode Integration:** Deeply integrated into the OpenCode terminal environment as a custom tool.

## Tech Stack (Verified)
- **Language:** Python (Main Orchestrator), TypeScript (OpenCode Plugin).
- **Mechanism:** LMSR (Logarithmic Market Scoring Rule).
- **Environment:** OpenCode Terminal / Headless Sessions.
- **Testing:** Oracle-based execution of agent-proposed verifiers.
