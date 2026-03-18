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
- **Rating Updates:** Ratings are updated periodically or after a batch of test results. Pass/fail results against different tests are weighted by the "difficulty" or "authority" of the test (see Section 4).
- **Volatility:** Captures erratic changes in performance (e.g., a massive refactor that fixes many bugs or introduces new ones).

## 3. Asynchronous Execution & Notifications

The tournament transitions from "rounds" to a continuous stream of events. Agents operate independently and are notified of significant changes in the environment.

### Notification System:
<!-- notifications function by interupting the agent (as if esc key is pressed - and sending a message) -->
Agents are subscribed to an event bus and receive notifications that trigger new inference/action cycles:

1.  **Submission Notification:** 
    - *Trigger:* "Candidate X (a rival) has submitted a new version of their code."
    - *Action:* Rival agents may choose to analyze the new code for vulnerabilities or inspiration.
<!-- easiness determined by relative elo rating - we can send the agent the k=3 easiest tests it failed every minute to avoid interrupting it too much-->
2.  **Failure Notification (Self):**
    - *Trigger:* "Your current submission failed Test Y (an 'Easy' or 'Native' test)."
    - *Action:* The agent is immediately prompted to fix the failing test. This creates a tight feedback loop for basic correctness.

<!-- need a discussion on prompt and what prompt contains for each notificatoin - reuse the existing diff calculatoin logic - when candidate proposes new code - send the diff just or that candidate - when verifier fails test - send verifier diff + stderr/stdout from the log - all of this needs to be truncated in prompt but also written to a location in agent wroktree where it can read the full output -->

<!-- this will require a different notificatoin system when making a dispaly for evalswe bench -->


<!-- need a sectoin on verifier interface - i think it needs to be a git patch + an entrypoint command - if patch fails to apply treat as draw - otherwise use exit code to determine win/loss -->
<!-- discuss hwo verifiers will be executed - whic his copy to a folder, patch agent, patch diff, run verifier - delete folder  -->
## 4. Verifiers and Baselines

To ensure a high standard of quality and a stable ground truth, the tournament incorporates specific "non-agent" participants.

<!-- just a regular verifier - elo rating determined like any other - probably need to have an llm produce verifier to identify the entrypoint into the test suite -->
### Native Test Suite as a Verifier:
- The project's existing test suite (if any) is included as a high-authority verifier.
- Failing a native test results in a significant rating penalty.
- Passing all native tests is a prerequisite for a high ELO rating.

### The "Empty Candidate" (Baseline):
- A "No-Change" candidate (the original codebase) is included as a participant.
- It never updates its code.
- It serves as a **lower-bound baseline**. Any candidate with a rating lower than the "Empty Candidate" is considered to have regressed the codebase.
- Rivals are incentivized to at least beat the baseline.

<!-- also need a section on agent interface - need to discuss actions, state machine , timeout/retry logic (whcih we can borrow from existing ocde) - i also want 2 kinds of agetns to execute in parallel - one working on candidates one working on tests - valid actions are update candidate for the candidate agens, and propose new test for the testing agents -->

<!-- agents need to only have access to their own workspace - they will not be allowed to look outside their `.` folder - accomplish this w/ opencode permissions and user groups -->

<!-- also need a section on orchestration - responsible for starting torunamne,t sending intial prompts, sending interrupts and updatd prompts on updates, scheduling and running tests, for now execute every test avaialble on every candidate update -->

## 5. Winning Criteria

<!-- lets just start w/ a time limit for now - by default lets have it be 3m -->
The tournament concludes when:
1.  **Rating Stability:** Ratings for the top candidates have converged (low $RD$).
2.  **Time/Budget Limit:** A hard limit is reached.

The winner is the candidate with the **highest Glicko-2 rating**, provided they pass a minimum threshold of native tests.

## 6. Comparison of Models
<!-- can delete this section -->
| Feature | LMSR Market (Design 1) | ELO Asynchronous (Design 2) |
| :--- | :--- | :--- |
| **Pace** | Synchronous Rounds (Wait for all) | Asynchronous (Fast feedback) |
| **Ranking** | Market Price (Credence) | Glicko-2 Rating (Skill) |
| **Feedback** | End of round summary | Real-time notifications |
| **Baseline** | Implicit (Whale prior) | Explicit (Empty Candidate) |
| **Complexity** | High (Economic theory) | Medium (Rating systems) |
| **Incentives** | Profit/Loss (Wealth) | Rating/Rank (Prestige/Survival) |
