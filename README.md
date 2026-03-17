## Usage

### Run a Tournament (Recommended)
The tournament is integrated as an OpenCode tool. To start a tournament, use the `opencode run` command:

```bash
opencode run "run a tournament with 3 agents for 10 rounds to implement a fast fibonacci function" --timeout 120
```

Or call the tool directly if your environment supports it:
- **Tool Name:** `tournament`
- **Arguments:** `prompt`, `rounds`, `agents`, `model`, `provider`, `target_file`, `log_level`, `timeout`

### Logging
You can control the verbosity of the tournament logs by passing the `log_level` parameter to the tool:

```bash
opencode run "run a tournament ... " --log_level INFO
```

#### Available Logging Levels:
- `DEBUG`: Extremely verbose. Shows all internal state transitions and raw API responses.
- `INFO`: (Recommended) Shows round progress, agent connectivity, and major market events.
- `WARNING`: Shows only issues like agent timeouts or failed patches.
- `ERROR`: (Default) Shows only critical crashes or system failures.

### Session Mapping
During the tournament, a `session_map.json` file is created in the arena directory (e.g., `.arenas/run_<timestamp>/session_map.json`). This map includes:
- `session_id`: The OpenCode session ID.
- `session_file`: Path to the actual JSON file containing the session history within the arena.
- `log_path`: Path to the human-readable log for that agent.

---

## Development

### Setup
Ensure you have Python 3.10+ and Node.js 18+ installed.

```bash
make setup
```

This will:
1. Install Python dependencies and perform an editable install of the project.
2. Install Playwright browsers.
3. Install Node.js dependencies in `.opencode/`.
4. Create a `.env` file from `.env.example`.

### Testing
You can run tests using the Makefile:

```bash
make test-python  # Run Python tests (pytest)
make test-js      # Run JS/TS tests (vitest)
make test-all     # Run both
```

Because of the editable install, you can also run `pytest` directly from the root directory. For JS tests, use `npx vitest` from within the `.opencode/` directory.

### Observing the Tournament
The tournament tool executes in your current TUI, blocking it until completion. To "swap in" and see what agents are doing live, you must use a **second terminal**.

#### 1. Attach to Session (Interactive TUI)
When the tournament starts, it will print a command like this:
```
[Tournament] Server started. To inspect agents, run in NEW terminal:
opencode attach http://127.0.0.1:45678
```
Copy and run that command in a new terminal window. You will be connected to the tournament's server. You can then use the standard UI to switch between agent sessions (e.g., `agent_0`, `agent_1`).

#### 2. Live Logs (Passive)
Each agent writes a detailed log. You can `tail` them to watch their "thought process":

```bash
# Find the arena directory from the output (e.g., .arenas/run_123456)
tail -f .arenas/run_123456/sessions/agent_0.log
```

### Manual CLI (Advanced)
If you need to run the market logic manually without the OpenCode tool wrapper:

```bash
python3 -m market.cli --log-level INFO run --prompt "Your coding problem" --agents 3 --rounds 10 --timeout 120
```

### Session Mapping
During the tournament, a `session_map.json` file is created in the arena directory (e.g., `.arenas/run_<timestamp>/session_map.json`). This map includes:
- `session_id`: The OpenCode session ID.
- `session_file`: Path to the actual JSON file containing the session history within the arena.
- `log_path`: Path to the human-readable log for that agent.

---

## Development

### Setup
Ensure you have Python 3.10+ and Node.js 18+ installed.

```bash
make setup
```

This will:
1. Install Python dependencies and perform an editable install of the project.
2. Install Playwright browsers.
3. Install Node.js dependencies in `.opencode/`.
4. Create a `.env` file from `.env.example`.

### Testing
You can run tests using the Makefile:

```bash
make test-python  # Run Python tests (pytest)
make test-js      # Run JS/TS tests (vitest)
make test-all     # Run both
```

Because of the editable install, you can also run `pytest` directly from the root directory. For JS tests, use `npx vitest` from within the `.opencode/` directory.

---