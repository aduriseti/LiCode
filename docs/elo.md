# Alternate Tournament Structure: ELO-based Asynchronous Competition

This document outlines an alternative design for the LiCode tournament, shifting from a synchronous, LMSR-based market to an asynchronous, ELO-rated competition.

## 1. High-Level Concept

In the current design, agents participate in discrete, synchronous rounds, betting on code quality and test outcomes using a Logarithmic Market Scoring Rule (LMSR). While theoretically robust, this can be slow and computationally expensive.

The **ELO-based Asynchronous Competition** treats candidates as players in a continuous tournament. Their "skill" (code quality) is estimated using a rating system (Glicko-2), and they receive real-time feedback as they and their rivals iterate.

## 2. Rating Mechanism: Glicko-2

Instead of market prices, we use the **Glicko-2** rating system to rank candidates. Glicko-2 improves upon ELO by tracking both a rating ($R$) and a rating deviation ($RD$), which represents the uncertainty in the rating.

### How it Works:
- **Initialization:** Every candidate starts with a default rating (e.g., $R=1500, RD=350, \text{volatility}=0.06$).
- **Matches:** A "match" occurs whenever a verifier (test) is executed against a candidate.
  - **Win:** Candidate passes the test.
  - **Loss:** Candidate fails the test.
  - **Draw:** Occurs if a verifier's patch fails to apply to a candidate.
- **Rating Updates:** Ratings are updated periodically or after a batch of test results. Pass/fail results against different tests are weighted by the "difficulty" (easiness determined by relative ELO rating) or "authority" of the test.
- **Volatility:** Captures erratic changes in performance (e.g., a massive refactor that fixes many bugs or introduces new ones).

## 3. Asynchronous Execution & Notifications

The tournament transitions from "rounds" to a continuous stream of events. Agents operate independently and are notified of significant changes in the environment via an interruption mechanism (similar to pressing the ESC key in a terminal), which sends a message directly to the agent session.

<!-- its interrupt then send a mesasge to the agent -->

### Notification System:
Agents are subscribed to an event bus and receive notifications that trigger new inference/action cycles:

1.  **Submission Notification:** 
    - *Trigger:* "Candidate X (a rival) has submitted a new version of their code."
    - *Action:* The orchestrator calculates the diff using the existing diff logic and sends it to rival agents. Agents may choose to analyze the new code for vulnerabilities or inspiration.
<!-- also need to write full candidate diff to a location in agent worktree  -->
    <!-- add prompt content here - diff will be t runcated but written to location in worktree also -->
2.  **Failure Notification (Self):**
    - *Trigger:* "Your current submission failed Test Y."
    - *Action:* To avoid over-interrupting agents, the orchestrator sends a batch of the $k=3$ easiest tests the agent is currently failing every minute.
    - *Prompt Content:* The notification includes the verifier diff and the `stderr/stdout` from the test log. This information is truncated in the prompt to preserve context but written in full to a specific location in the agent's worktree for detailed analysis.


## 4. Verifier and Agent Interfaces

### Verifier Interface & Execution:
Verifiers are defined as a combination of a git patch and an entrypoint command.
- **Execution Flow:**
  1. Copy the candidate's worktree to a temporary execution folder.
  2. Apply the candidate's code changes.
  3. Apply the verifier's git patch.
  4. Run the entrypoint command.
  5. Delete the temporary folder.
  <!-- actually instead of a draw just dont perform any rating update -->
- **Result:** Exit code 0 indicates a **Win** for the candidate (Pass); non-zero indicates a **Loss** (Fail). If the verifier's patch fails to apply, the result is a **Draw**.

### Agent Interface & Types:
The system executes two types of agents in parallel, borrowing the existing state machine and timeout/retry logic from the current orchestrator:
- **Candidate Agents:** Primary goal is to improve their solution. Valid action: `update_candidate`.
- **Testing Agents:** Primary goal is to find bugs in other solutions. Valid action: `propose_new_test`.

### Permissions & Isolation:
Agents are strictly restricted to their own workspace. They are not permitted to look outside their `.` folder. This isolation is enforced using OpenCode's internal permission system and OS-level user groups.

## 5. Orchestration

The Orchestrator is responsible for:
- Starting the tournament and sending initial problem prompts.
- Sending interrupts and updated prompts based on event triggers.
- Scheduling and running tests. By default, every available test is executed against every candidate whenever a candidate submits an update.
- Managing the state machine and handling agent timeouts.

## 6. Verifiers and Baselines

### Native Test Suite as a Verifier:
An LLM is used to analyze the codebase and identify the correct entrypoint into the native test suite. Otherwise treated as any other verifier.

### The "Empty Candidate" (Baseline):
A "No-Change" candidate representing the original codebase is included. It serves as a lower-bound baseline; any candidate with a rating lower than the baseline has regressed the code. Rivals are incentivized to at least beat the baseline rating.

<!-- include a sectin on se bench integration and ui - i dont want to have a dashboard for this - lets just rely on trace logging and other logs for now - lets clone swe bench script for this to accompade differences in interface -->

## 7. Winning Criteria

The tournament concludes based on:
1.  **Time Limit:** A default hard limit of (by default) 3 minutes.
2.  **Rating Stability:** Convergence of Glicko-2 ratings (low $RD$) for the top-tier candidates.

The winner is the candidate with the **highest Glicko-2 rating**, provided they pass a minimum threshold of native tests.
