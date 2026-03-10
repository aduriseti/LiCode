# Implementation Plan: Containerized Inference for SWE-bench

## Phase 1: Docker Environment Infrastructure
Goals: Resolve SWE-bench images and manage container lifecycles programmatically.

- [ ] Task: Create Docker utility module
    - [ ] Write tests for architecture detection and image resolution.
    - [ ] Implement `resolve_image_name(instance_id)` using GHCR patterns.
    - [ ] Implement `get_container_id(instance_id)` to check for running containers.
- [ ] Task: Implement Container Lifecycle Manager
    - [ ] Write tests for container start/stop/pull.
    - [ ] Implement `start_task_container(instance_id, work_dir, licode_dir)` with volume mounts.
    - [ ] Implement `stop_task_container(container_id)` with reliable cleanup.
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Docker Infrastructure' (Protocol in workflow.md)

## Phase 2: In-Container Market Execution
Goals: Bootstrap LiCode dependencies and run the market process inside the container.

- [ ] Task: Implement Bootstrap Script
    - [ ] Write tests for dependency installation check.
    - [ ] Implement logic to run `pip install` inside the target container during setup.
- [ ] Task: Refactor `evaluate_swe_bench.py` for In-Container Run
    - [ ] Write integration tests for `docker exec` market command generation.
    - [ ] Update `run_market_on_instance` to delegate execution to the container.
    - [ ] Ensure `PYTHONPATH` and environment variables are correctly passed to the container.
- [ ] Task: Conductor - User Manual Verification 'Phase 2: In-Container Execution' (Protocol in workflow.md)

## Phase 3: Integration & Validation
Goals: Verify that containerization resolves the "Blindness" and "Drift" failure modes.

- [ ] Task: End-to-End Validation
    - [ ] Run `astropy__astropy-13033` and verify `pytest` execution success.
    - [ ] Run `django__django-13195` and verify string format parity.
    - [ ] Ensure all 10 hardest tasks apply patches correctly.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Integration & Validation' (Protocol in workflow.md)
