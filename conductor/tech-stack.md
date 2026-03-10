# Technology Stack: LiCode (Logical Induction Market)

## Overview
LiCode is a hybrid Python and TypeScript/Node.js project designed for highly concurrent, resource-competitive agent tournaments. It leverages the OpenCode AI framework for agent execution and the Logarithmic Market Scoring Rule (LMSR) for truth-finding via consensus.

## Core Backend (Python)
- **Primary Language:** Python (3.x)
- **Concurrency:** `asyncio` for non-blocking orchestration of multiple agent sessions and market rounds.
- **Economic Engine:** Custom implementation of the Logarithmic Market Scoring Rule (LMSR) with Batch Wager Clearing.
- **Agent Orchestration:** `opencode-ai` for managing headless agent sessions and tool calls.
- **Containerization:** Docker for executing tournaments in official task-specific environments (GHCR images).
- **Reliability:** `tenacity` for robust error handling and retries during agent inference and tool execution.
- **CLI/Logs:** `rich` for formatted logging and high-signal TUI feedback.
- **Configuration:** `python-dotenv` for centralized environment variable management.

## Dashboard & Tooling (Node.js/TypeScript)
- **Primary Language:** TypeScript
- **Web Server:** `express` (v5.x) for serving the browser-based dashboard.
- **Real-time Communication:** `socket.io` for streaming live market events, price trajectories, and agent logs to the dashboard.
- **Terminal Management:** `node-pty` for efficient terminal emulation and PTY handling within the dashboard.
- **Plugin System:** `@opencode-ai/plugin` for seamless integration as an OpenCode tool.

## Storage & Persistence
- **In-Memory State:** Current market state (prices, shares, wealth) is maintained in memory for high-speed atomic rounds.
- **Snapshot Serialization:** Complete market state is periodically serialized to JSON for crash recovery and post-tournament analysis.
- **Agent Sessions:** Individual agent history and context are stored in isolated SQLite databases (via OpenCode).

## Quality Assurance
- **Python Testing:** `pytest` (with `pytest-asyncio` and `pytest-timeout`) for market logic and orchestrator integration tests.
- **Node.js Testing:** `vitest` for dashboard and plugin logic.
- **E2E Testing:** `playwright` for end-to-end verification of the browser-based dashboard.
