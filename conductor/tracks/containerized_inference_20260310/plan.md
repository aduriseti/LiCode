### Implementation Plan: Containerized Inference for SWE-bench

#### Phase 1: Docker Infrastructure [checkpoint: fde9264]
- [x] Task: Implement `market/core/docker.py` for image resolution and container management b78a59a
    - [x] Create unit tests for `get_image_name` (strict x86_64 resolution)
    - [x] Implement image resolution using Epoch research GHCR pattern
    - [x] Create tests for container start/stop/exec wrappers
    - [x] Implement Docker lifecycle wrappers using `subprocess`
- [x] Task: Conductor - User Manual Verification 'Docker Infrastructure' (Protocol in workflow.md)

#### Phase 2: Orchestration Refactor [checkpoint: 48c9545]
- [x] Task: Update `evaluate_swe_bench.py` to manage containerized tournaments f3e45d3
    - [x] Write integration test for container lifecycle in evaluation flow
    - [x] Integrate container start/stop into the `run_market_on_instance` loop
    - [x] Implement the `Bootstrap` step (pip install LiCode deps inside container)
- [x] Task: Modify tournament execution to use `docker exec` f3e45d3
    - [x] Write test verifying command routing to container
    - [x] Refactor market command generation to use `docker exec` with mounted paths
- [x] Task: Conductor - User Manual Verification 'Orchestration Refactor' (Protocol in workflow.md)
#### Phase 3: Validation & Cleanup [checkpoint: a333365]
- [x] Task: End-to-End Validation a333365
    - [x] Verify `astropy__astropy-13033` passes `pytest` (confirming `setuptools_scm` access)
    - [x] Verify `django__django-13195` string formatting matches container expectations
    - [x] Verify zero container leakage on process interruption
- [x] Task: Fix OpenCode Agent Startup Authentication a333365
    - [x] Remove hardcoded `~/.local/share/opencode/auth.json` symlink logic from `market/runner.py`
    - [x] Ensure `OPENCODE_API_KEY` is passed via `docker exec` in `evaluate_swe_bench.py`
    - [x] Update `market/cli.py` default model to `gemini-2.5-flash`
- [x] Task: Implement Centralized .env Configuration a333365
    - [x] Create `.env.example` with standard LLM and OpenCode config placeholders
    - [x] Add `python-dotenv` to `requirements.txt`
    - [x] Integrate `load_dotenv()` into `evaluate_swe_bench.py` and `market/cli.py`
- [x] Task: Conductor - User Manual Verification 'Validation & Cleanup' (Protocol in workflow.md) a333365
