# Specification: Containerized Inference for SWE-bench

## Overview
Implement a "Tournament in a Box" architecture where the entire LiCode market process runs inside the task-specific SWE-bench Docker container. This ensures that agents have perfect environment parity, access to all build tools (like `setuptools_scm`), and the correct library versions during the inference phase.

## Functional Requirements
1. **Dynamic Image Resolution**: Detect host architecture and resolve the GHCR image ID for a given `instance_id` using the Epoch AI pattern (`ghcr.io/epoch-research/swe-bench.eval.x86_64.{instance_id}:latest`).
2. **Container Lifecycle Management**: Automate pulling the image, starting the container in the background, and ensuring it is stopped/removed after the tournament (even on failure).
3. **In-Container Execution**: Execute `market.cli` inside the container via `docker exec`.
4. **Bootstrap Phase**: Automatically install LiCode dependencies from `requirements.txt` into the container before starting the market.
5. **Volume Mounting**:
    - Mount the LiCode source code from the host into the container (read-only).
    - Mount the instance worktree (the repo to be fixed) into the container at `/testbed` (read-write).

## Non-Functional Requirements
- **Hardware Initial Support**: Initially target `x86_64` only.
- **Reliability**: Use `docker exec` return codes to fail fast if the environment setup or bootstrap fails.

## Acceptance Criteria
- [ ] `evaluate_swe_bench.py` successfully resolves and starts a Docker container for a given task.
- [ ] Agents can successfully run `pytest` inside the container using project-specific tools (e.g., `setuptools_scm`).
- [ ] The generated `patch.diff` accurately reflects changes made inside the container.
- [ ] Containers are reliably cleaned up after evaluation.

## Out of Scope
- Dynamic multi-architecture support (ARM64).
- Creating custom Docker images for non-SWE-bench repositories.
