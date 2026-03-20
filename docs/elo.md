# Alternate Tournament Structure: ELO-based Asynchronous Competition

This document outlines an alternative design for the LiCode tournament, shifting from a synchronous, LMSR-based market to an asynchronous, ELO-rated competition.

## 1. High-Level Concept

In the current design, agents participate in discrete, synchronous rounds, betting on code quality and test outcomes using a Logarithmic Market Scoring Rule (LMSR). While theoretically robust, this can be slow and computationally expensive.

The **ELO-based Asynchronous Competition** treats candidates as players in a continuous tournament. Their "skill" (code quality) is estimated using a rating system (Glicko-2), and they receive real-time feedback as they and their rivals iterate.

## 2. Rating Mechanism: Glicko-2

Candidates and Verifiers are rated using the **Glicko-2** system. To maintain accuracy as candidates iterate, the system employs **Candidate Versioning**.

### Versioning and "Episode" Resets:
- **Immutable Versions:** Every time a candidate submits a code update, a new **Version** is created.
- **Match Pinning:** A match (test execution) is pinned to a specific version of a candidate. The result of that match (Win/Loss) only impacts the rating of that specific version.
- **Rating Inheritance (The "Bayesian Prior"):** A new version inherits the rating ($R$) from its predecessor, but its Rating Deviation ($RD$) is reset to the maximum (350).
    - **Formal Justification:** This treats the code update as a **non-stationary skill shift**. The old rating serves as the **Maximum A Posteriori (MAP)** estimate—the best available guess for the new code's quality.
    - **Learning Rate Recovery:** Resetting $RD$ to 350 "unlocks" the rating, allowing it to move rapidly if the new code's performance differs from the old, while starting from a statistically informed "prior" location.
- **Leaderboard:** The tournament leaderboard displays the rating of the **most recent version** for each candidate.

## 3. Asynchronous Execution & Notifications

The tournament transitions from "rounds" to a continuous stream of events. 

### Reactive Test Execution:
The orchestrator automatically schedules matches in the following scenarios to ensure rapid rating convergence:
- **Candidate Update:** Whenever a candidate creates a new version (submits an update), it is automatically scheduled for matches against **every available verifier**.
- **Verifier Addition:** Whenever a new verifier is added to the tournament (e.g., by a testing agent), it is automatically scheduled for matches against the **latest version of every candidate**.

### Notification System:
Agents are subscribed to an event bus and receive notifications that trigger new inference/action cycles. To prevent context flooding and excessive task switching, notifications are **batched and throttled** (minimum 30 seconds between interrupts).

1.  **Submission Notification:** 
    - *Trigger:* "Candidate X (a rival) has submitted a new version of their code."
    - *Action:* The orchestrator calculates the diff. A **truncated** version (first 50 lines) is sent via notification, while the **full diff** is saved to the agent's worktree under `.diffs/vN.diff`.
2.  **Failure Notification (Self):**
    - *Trigger:* "Your current submission (Version N) failed Test Y."
    - *Action:* The orchestrator writes the **full execution log** (stdout/stderr) to the agent's worktree at `.test_logs/vN_vs_testY.log`. A notification is sent containing a **truncated error log** (last 50 lines) and the absolute path to the full log file. Notifications are batched to include the easiest failing tests for the *latest* version.

## 4. Verifier and Agent Interfaces

### Verifier Interface & Execution:
Verifiers are defined as a combination of a git patch and an entrypoint command.
- **Execution Flow:**
  1. Copy the candidate's worktree to a temporary execution folder.
  2. Apply the candidate's code changes.
  3. Apply the verifier's git patch.
  4. Run the entrypoint command.
  5. Delete the temporary folder.
- **Result:**
  - **Win (PASS):** Exit code 0. Candidate rating increases.
  - **Loss (FAIL):** Non-zero exit code. This includes cases where the test command itself implements an internal timeout and exits with an error. Candidate rating decreases.
  - **Skip (currently just PATCH_ERROR):** If a verifier's patch fails to apply (PATCH_ERROR). **No rating update is performed.**

### Agent Interface & Types:
The system executes two types of agents in parallel, borrowing the existing state machine and timeout/retry logic from the current orchestrator.

- **Candidate Agents:** Primary goal is to improve their solution by modifying their own code and fixing reported bugs.
- **Testing Agents:** Primary goal is to act as **Verifiers** by writing tests that can accurately distinguish between correct solutions and buggy ones. They are not direct rivals to the candidates; instead, they are rated on the authority and discriminative power of their tests.

### Agent Action Interface:
Agents interact with the tournament by modifying their local directory (workspace) and then submitting a single JSON action in their final response.

1.  **`update_candidate`**: Used by Candidate Agents to submit a new version of their solution.
    - **Mechanism:** The system computes the diff between the agent's current workspace and the **`baseline`** git tag (created during workspace initialization). This ensures that even if the agent makes local commits, the full delta from the original state is captured.
    - **Required JSON:** `{"action": "update_candidate", "message": "Summary of changes"}`
2.  **`propose_test`**: Used by Testing Agents to submit a new verifier to the tournament.
    - **Mechanism (The Overlay):** 
        1. The system computes the diff of the testing agent's workspace.
        2. This diff (the "test package") is bundled together.
        3. To run the test against a rival: A clean copy of the rival's candidate worktree is created.
        4. The "test package" is **overlaid** (applied) onto that copy.
        5. The `entrypoint` command is executed from the root of that project.
    - **Required JSON:** `{"action": "propose_test", "entrypoint": "bash run_my_test.sh"}`

### Permissions & Isolation:
Agents are strictly restricted to their own workspace (e.g., `/workspaces/LiCode/.arenas/elo_run_1773939483/worktrees/candidate_0`). They are not permitted to look outside their assigned folder. This isolation is enforced using OpenCode's internal permission system and OS-level user groups. All actions, including code modifications and test submissions, are performed within this isolated environment.

### Agent State Machine & Lifecycle:
Agents are managed via an explicit state machine to ensure robust behavior and clean termination:

- **`UNINITIALIZED`**: Initial state before the tournament boots.
- **`INITIALIZING`**: Spawning the OpenCode server and creating the session.
- **`THINKING`**: Actively engaged in an LLM `chat` cycle (including multi-turn tool-use loops).
- **`WAITING`**: The agent has submitted its work (e.g., `update_candidate`) and is idle until a new event occurs.
- **`ERROR`**: The agent encountered a fatal exception.
- **`TERMINATED`**: Tournament complete; resources released.

### State Transition Matrix:

| Current State | Event / Trigger | End State | Description |
| :--- | :--- | :--- | :--- |
| `UNINITIALIZED` | `initialize()` | `INITIALIZING` | Booting server and creating session. |
| `INITIALIZING` | `Success` | `THINKING` | Server ready; starting action loop. |
| `THINKING` | `Action: update_candidate` | `WAITING` | Code committed; agent idle until next event. |
| `THINKING` | `Action: propose_test` | `THINKING` | Test added; agent continues iteration. |
| `THINKING` | `Error (e.g. Malformed JSON)` | `THINKING` | Feedback sent; agent retries in current turn. |
| `THINKING` | **`INTERRUPT`** | `THINKING` | **The Pivot:** Ongoing task aborted; loop restarts with new data. |
| `WAITING` | **`INTERRUPT`** | `THINKING` | **The Wakeup:** Idle agent receives new event (e.g., rival update). |
| *Any* | `shutdown()` | `TERMINATED` | Tournament complete; loop broken and server killed. |

### The Interrupt (Pivot) Mechanism:
The Orchestrator uses interruptions to "pivot" agents when higher-priority events occur (e.g., a rival submission or a test failure). 

- **Aggressive Abort:** An interrupt aggressively **aborts** any ongoing LLM task (even if the agent is in the `THINKING` state) and immediately restarts the loop with the new information.
- **Batching & Throttling:** Interrupts are sent at most once every 30 seconds per agent. If multiple events occur within this window, they are consolidated into a single batched interrupt message.
- **Persistence:** All notification data (messages and metadata) are written to the agent's worktree under `.interrupts/` for auditability and recovery.

## 5. Orchestration

The Orchestrator is responsible for:
- Starting the tournament and sending initial problem prompts.
- Sending interrupts and updated prompts based on event triggers.
- Scheduling and running tests. By default, every available test is executed against every candidate whenever a candidate submits an update.
- Managing the state machine and handling agent timeouts.

## 6. Verifiers and Baselines

### Native Test Suite as a Verifier:
The project's existing test suite is included as a high-authority verifier. An LLM is used to analyze the codebase and identify the correct entrypoint into the native test suite. Otherwise, it is treated like any other verifier.

### The "Empty Candidate" (Baseline):
A "No-Change" candidate representing the original codebase is included. It serves as a lower-bound baseline; any candidate with a rating lower than the baseline has regressed the code. Rivals are incentivized to at least beat the baseline rating.

## 7. SWE-bench Integration and UI

To maintain simplicity and focus on diagnostic depth, the ELO tournament will not utilize a live dashboard. Instead, the system will rely on exhaustive trace logging and standard output logs for monitoring and post-hoc analysis. The existing `eval_swe_bench` script will be cloned and modified to accommodate the unique asynchronous interface and notification requirements of this tournament structure.

## 8. Winning Criteria

The tournament concludes based on:
1.  **Time Limit:** A default hard limit of (by default) 3 minutes.
2.  **Rating Stability:** Convergence of Glicko-2 ratings (low $RD$) for the top-tier candidates.

The winner is the candidate with the **highest Glicko-2 rating**.
