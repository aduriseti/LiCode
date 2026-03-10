### Specification: Containerized Inference for SWE-bench

#### Overview
This track implements an "All-in-Container" execution model for SWE-bench evaluations. The entire LiCode tournament process (orchestrator, agents, and verifiers) will run inside the official task-specific SWE-bench Docker container. This eliminates environment "blindness" (missing build tools) and "drift" (formatting differences) by ensuring perfect parity between inference and final evaluation.

#### Functional Requirements
1.  **Image Resolution**: Automatically resolve the official Epoch AI GHCR image ID for a given `instance_id` using the strict `x86_64` architecture.
2.  **Container Management**: Implement synchronous lifecycle management (Pull -> Start -> Exec -> Stop -> Remove) for each task instance in `evaluate_swe_bench.py`.
3.  **Volume Mounting**: 
    *   Mount the LiCode source code to `/licode`.
    *   Mount the task repository worktree to `/testbed`.
4.  **On-Demand Bootstrapping**: Automatically install LiCode's Python dependencies (`requirements.txt`) into the container's environment before starting the tournament.
5.  **Remote Execution**: Execute the market tournament via `docker exec` using the container's internal paths and Python environment.
6.  **Isolation**: Ensure every task run is isolated within its own ephemeral container instance.

#### Non-Functional Requirements
1.  **Security**: Use `--no-hardlinks` during clones and restricted container permissions to ensure agent worktrees cannot leak between instances.
2.  **Reliability**: Robustly handle Docker daemon failures and ensure container cleanup even if the tournament process crashes.
3.  **Observability**: Stream logs from inside the container back to the host `main.log` and the dashboard.

#### Acceptance Criteria
1.  `evaluate_swe_bench.py` successfully resolves and pulls a SWE-bench Docker image for a specific task.
2.  The market tournament executes successfully inside the container using the container's Python interpreter.
3.  Agents can run `pytest` inside the container and access build-time dependencies (like `setuptools_scm`) that are not present on the host.
4.  The container is automatically stopped and removed after the tournament finishes.

#### Out of Scope
*   Caching "patched" Docker images with LiCode dependencies pre-installed (future optimization).
*   Supporting `arm64` native images (strictly `x86_64` for now).
*   Persistent container pools.
