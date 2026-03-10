### Implementation Plan: Containerized Inference for SWE-bench

#### Phase 1: Docker Infrastructure
- [ ] Task: Implement `market/core/docker.py` for image resolution and container management
    - [ ] Create unit tests for `get_image_name` (strict x86_64 resolution)
    - [ ] Implement image resolution using Epoch research GHCR pattern
    - [ ] Create tests for container start/stop/exec wrappers
    - [ ] Implement Docker lifecycle wrappers using `subprocess`
- [ ] Task: Conductor - User Manual Verification 'Docker Infrastructure' (Protocol in workflow.md)

#### Phase 2: Orchestration Refactor
- [ ] Task: Update `evaluate_swe_bench.py` to manage containerized tournaments
    - [ ] Write integration test for container lifecycle in evaluation flow
    - [ ] Integrate container start/stop into the `run_market_on_instance` loop
    - [ ] Implement the `Bootstrap` step (pip install LiCode deps inside container)
- [ ] Task: Modify tournament execution to use `docker exec`
    - [ ] Write test verifying command routing to container
    - [ ] Refactor market command generation to use `docker exec` with mounted paths
- [ ] Task: Conductor - User Manual Verification 'Orchestration Refactor' (Protocol in workflow.md)

#### Phase 3: Validation & Cleanup
- [ ] Task: End-to-End Validation
    - [ ] Verify `astropy__astropy-13033` passes `pytest` (confirming `setuptools_scm` access)
    - [ ] Verify `django__django-13195` string formatting matches container expectations
    - [ ] Verify zero container leakage on process interruption
- [ ] Task: Conductor - User Manual Verification 'Validation & Cleanup' (Protocol in workflow.md)
