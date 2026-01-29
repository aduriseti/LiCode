# OpenCode Logical Induction Market: System Specification (v1.0)
==============================================================

**Context:** A resource-competitive software engineering tournament implemented within the `OpenCode` terminal environment. 

**Theoretical Foundation:** Computable approximation of _Logical Induction_ ([Garrabrant et al., 2016](https://arxiv.org/abs/1609.03543)). 

* * *

1\. High-Level Concept & Motivation
-----------------------------------

### The Core Problem

Current Agentic coding systems (like Devin or standard RAG loops) typically rely on a single model checking itself ("Self-Reflection"). This is fragile; models often hallucinate that their own broken code works. Parallel sampling ("Best-of-N") generates many options but lacks a rigorous, automated way to select the winner without expensive human review.

### The Solution: A Market for Logical Claims
<!-- WTF is a bounded trader - explain the lgoical induction paper & terminology and how it relates to this probelm -->


This system is motivated by the _Logical Induction Criterion_, which states that a market of bounded traders will eventually assign probabilities to logical statements that respect the rules of deduction. In our context, "logical statements" are claims about the code's behavior (e.g., "This function crashes with null input").

We replace the single "Judge" with a **Market**.
<!-- you need to make it more clear how sentence proposal generates wealth - why are agents incentivised to propose sentances? -->
<!-- explain how sentences relate to actions like writing code or tests - remember that a sentence is not the same about an action - it is a belief instead -->
<!-- this should be an iterative pro -->
*   **The Incentive:** Agents are paid to make accurate predictions about the outcomes of running code
*   **The Mechanism:** The system is built around two key actions:
    *   **Sentence Proposal:** Agents make formal claims about the code. A "sentence" can be a new code implementation, a new test case, or a static analysis claim. Each sentence is a tradeable asset in the market.
    *   **Verifier Proposal:** For a sentence to be resolvable, it needs a "verifier"—an executable script (like a unit test) that determines its truth value.
    If Agent A proposes new code, and Agent B proposes a verifier (a test) that breaks it, Agent B's bet against Agent A's code will pay off, transferring wealth from A to B.
*   **The Result:** The system naturally filters out hallucinations because they are "expensive" to maintain against adversarial attacks.

<!-- what ist he property of this system? hwo does this let us select good code and drive iteration on code? -->


* * *

## 2. Operational Workflow (Plain English)

### Phase A: Initialization (The Bootstrap)

The system begins when the user provides a prompt `$P_{user}$` and a budget.

1.  **The Goal:** The system registers the Master Sentence $\varphi_{goal}$ : _"The code satisfies the user's prompt."_ This is the ultimate, (usually) unverifiable sentence that all other claims are proxies for.
2.  **The Seed:** A **baseline agent** generates a "Strawman" code candidate ( $C_{0}$ ). This agent is typically a straightforward, non-adversarial LLM tasked with providing a plausible first attempt. It is likely buggy, but it provides the initial asset for trading.
3.  **The Capital:** $M$ **competing agents** are spawned. These are distinct, stateful LLM sessions, each initialized with an equal bankroll of "Compute Credits" ( $W_{0}$ ). Their goal is to increase their wealth by making accurate predictions.

### Phase B: The Trading Round (The "Heartbeat")

The orchestrator (also called the **market arbitrator**) runs a discrete loop of **Inference and Trade**:

1.  **Observation:** The arbitrator broadcasts the current market state to all active agents. This state includes:
    *   The full set of active sentences $\Phi_t$ (code, tests, claims).
    *   The source code and associated verifiers for these sentences.
    *   The current consensus market prices $P_t$ for all sentences.
    *   *(Design Choice): Whether to include other agents' belief vectors is an experimental parameter. Full transparency could lead to herd behavior, while opacity might reduce the market's efficiency.*
2.  **Inference:** Agents use their internal "thought" processes (e.g., Chain-of-Thought) and local tools (linters, debuggers, static analyzers) to analyze the assets and form private beliefs about their validity.
3.  **Belief Formulation:** Based on their analysis, agents form internal probability estimates for each sentence (e.g., "I am 99% sure Candidate $C_{0}$ fails on edge case $X$").
4.  **Action:** Agents submit their desired actions to the arbitrator.
    *   **Propose:** Agents can pay a fee $\gamma$ to register new sentences.
        *   **Requirement:** Any new sentence $\varphi_{new}$ must be accompanied by a **verifier** $V_{\varphi_{new}}$ (e.g., a unit test). The arbitrator can and should reject sentences without a well-formed verifier. This prevents a glut of untestable claims. The primary incentive to register a sentence is to trade on it; if an agent discovers a flaw, it can propose a failing test case and bet heavily on its failure, expecting a large payout.
        *   **Automation:** The arbitrator can be configured to automatically generate sentences for certain actions. For example, if an agent submits a piece of code that looks like a unit test, the arbitrator can wrap it in a formal sentence/verifier structure.
    *   **Bet:** Agents submit a **Belief Vector** $b_i$ to the market, reporting their probability for each sentence. Disagreements with the consensus price $P_t$ are treated as implicit bets. If an agent fails to report a belief for a given sentence, it is assumed to be neutral (i.e., its belief matches the current market price, $b_{i,t}(\varphi) = P_t(\varphi)$), resulting in no bet.
5.  **Market Update:** The arbitrator gathers all belief vectors and updates the consensus prices based on the new "Wealth-Weighted" beliefs of the agents.

### Phase C: Settlement (The Oracle)

Periodically, the arbitrator selects a batch of verifiable sentences for settlement.

1.  **Execution:** The arbitrator, acting as the **Oracle**, executes the verifier script $V_\varphi$ for each selected sentence $\varphi$ in a sandboxed environment.
    *   **Resource Constraints:** Verifiers are run with strict time and memory limits. If a verifier exceeds these limits, it is marked as `TIMEOUT`, and the sentence's truth value is considered unresolved for this round (effectively $\perp$). Agents can propose new sentences claiming a verifier will time out.
    *   **Unexecutable Verifiers:** If a verifier fails to execute due to syntax errors or other issues, it is marked `ERROR` and the sentence is unresolved ($\perp$).
2.  **Payout:** The arbitrator updates agent wealth based on the outcomes. For each sentence $\varphi$ that resolved to 0 or 1, the arbitrator calculates the payout $\Pi_i(\varphi)$ for each agent based on the scoring rule. Wealth is redistributed—agents who correctly predicted the outcome ("surprised the market") gain wealth from those who were wrong.
3.  **Bankruptcy:** Agents whose wealth $W_i$ drops below a certain threshold are terminated and removed from the market. This ensures that consistently poor predictors are culled.

* * *

3\. The Agent as a Session Trace
--------------------------------

In this implementation, an agent is not just a stateless model API call; it is a **Stateful LLM Session** managed by the tournament orchestrator.

*   **Identity:** Each agent is a separate `opencode` session with its own persistent filesystem and history. This allows it to maintain a "Chain of Thought," build on previous analysis, and develop complex strategies across multiple market rounds.
*   **The Toolset:** The tournament orchestrator provides a set of tools to each agent. These are wrappers around the core market mechanics.
    *   `read_market_state()`: A custom tool that returns a structured representation (e.g., JSON) of the public market state (sentences, verifiers, prices).
    *   `run_shell_command(command)`: The standard `opencode` tool for executing arbitrary shell commands in the agent's private workspace. This is used for all local analysis, such as running linters, compilers, or test suites on code candidates.
    *   `propose_sentence(description, verifier_path)`: A custom tool that allows an agent to submit a new sentence to the market arbitrator. The `verifier_path` must point to an executable file in the agent's workspace.
    *   `submit_belief(belief_vector)`: A custom tool for submitting the agent's belief vector to the arbitrator.

> **Example Trace (within an `opencode` session):**
>
> *   **Thought:** "The market is pricing the current code candidate `candidate_a.py` suspiciously high. I'll check for common errors. I'll start by checking for dependency issues."
> *   **Action:** `run_shell_command("pip check candidate_a.py")`
> *   **Observation (from stdout):** `Result: aiohttp 3.8.1 has requirement multidict<7.0,>=4.5, but you have multidict 4.4.`
> *   **Thought:** "Aha! A dependency conflict. This will cause a runtime error. I will create a verifier that demonstrates this, propose it as a new sentence, and bet heavily against the current candidate."
> *   **Action:** `write_file('verify_dep.py', 'import pkg_resources; pkg_resources.require("aiohttp==3.8.1")')`
> *   **Action:** `propose_sentence("Candidate_A fails dependency check", verifier_path="verify_dep.py")`
> *   **Action:** `submit_belief({"candidate_a_valid": 0.01, "dep_check_fails": 0.99})` (Shorting the original code, Longing the new failure sentence).

* * *

4\. Formal System Specification
-------------------------------

The market is defined as a discrete-time dynamical system $\Sigma = \langle A, \Phi, W, O \rangle$.

*   **$A$**: The set of $m$ Agents, $A = \{a_1, ..., a_m\}$.
*   **$\Phi_t$**: The set of active Logical Sentences at round $t$.
*   **$W_t \in \mathbb{R}_{\ge 0}^m$**: The Wealth Vector of compute credits for each agent at round $t$.
*   **$O:\Phi \to \{0,1,\perp\}$**: The Oracle function, which resolves the truth value of a sentence.

### A. The Assets: Sentences & Oracles

Every tradeable asset is a **Sentence** $\varphi$, which is a claim about the system.

*   **Sentence Requirement:** Every proposed sentence $\varphi$ must be accompanied by a **Verifier** $V_\varphi$. The arbitrator will reject sentences without a valid, executable verifier. This is a primary mechanism to prevent a flood of useless or untestable sentences.
*   **Verifier-Sentence Mismatch:** It is possible for an agent to propose a verifier that does not logically correspond to its sentence description (e.g., a sentence "The code is bug-free" with a verifier `assert 1==1`). The system does *not* attempt to semantically validate this link. Instead, it is the responsibility of other agents in the market to identify this mismatch, propose a new sentence exposing the flawed verifier (e.g., "The verifier for $\varphi_{123}$ is trivial"), and bet accordingly. This is part of the adversarial process.
*   **Computability:** While verifiers are required to be syntactically valid executable code, they may in practice be non-computable (e.g., contain an infinite loop) or exceed resource constraints. This is handled by the Oracle.

### B. The Oracle Function (O)

The Oracle resolves sentences. For a given sentence $\varphi$:
*   $O(\varphi) = 1$ if $Exec(V_\varphi)$ runs successfully and returns `True`.
*   $O(\varphi) = 0$ if $Exec(V_\varphi)$ runs successfully and returns `False`.
*   $O(\varphi) = \perp$ (Undefined) in all other cases. This includes:
    *   The verifier $V_\varphi$ is syntactically invalid or fails to compile.
    *   The verifier $V_\varphi$ exceeds its resource limits (timeout, memory).
    *   The sentence is inherently unverifiable (like $\varphi_{goal}$).
Bets on sentences that resolve to $\perp$ do not settle in the current round. The wealth invested in them is effectively frozen until they can be resolved, creating a strong incentive for agents to only propose and bet on decidable, efficient claims.

### C. Consensus Price ( $P_{t}$ )

The Market Price is the **Wealth-Weighted Centroid** of agent beliefs. Let $b_{i,t}(\varphi)$ be the belief (a probability estimate from 0 to 1) of agent $a_i$ on sentence $\varphi$ at time $t$.

$$
P_{t}\left(\varphi \right)=\frac{\sum_{i=1}^{m} W_{i,t}\cdot b_{i,t}\left(\varphi \right)}{\sum_{i=1}^{m} W_{i,t}}
$$

*   **Relation to Logical Induction:** This formulation is directly inspired by the update rule in Logical Induction. The market's price represents the most credible current belief, giving more weight to agents who have proven to be more accurate in the past (i.e., have more wealth).
*   **Relation to Kelly Criterion:** While not a direct implementation, the principle is related. The Kelly criterion suggests that bet size should be proportional to the edge (the difference between your belief and the odds). Here, an agent's "bet" is implicitly its belief's deviation from the market price. The wealth-weighting means agents with more capital (who have "survived" longer) are effectively making larger, more influential bets, similar to a Kelly gambler with a larger bankroll.

### D. The Payout (Logarithmic Scoring Rule)

Wealth is updated based on **Information Gain**. The payout $\Pi_{i,t}$ for agent $a_i$ on a single sentence $\varphi$ that resolves to an outcome $o_\varphi \in \{0,1\}$ is calculated using a logarithmic scoring rule (log loss):

$$
\Pi _{i,t}\left(\varphi \right)=\alpha \cdot W_{i,t}\cdot \left[o_{\varphi }\ln \left(\frac{b_{i,t}\left(\varphi \right)}{P_{t}\left(\varphi \right)}\right)+\left(1-o_{\varphi }\right)\ln \left(\frac{1-b_{i,t}\left(\varphi \right)}{1-P_{t}\left(\varphi \right)}\right)\right]
$$

*   **Why Logarithmic Scoring?** This is a "proper scoring rule," which means it incentivizes agents to report their true beliefs. The maximum expected payout occurs when an agent submits $b_i(\varphi)$ equal to their true internal probability estimate.
*   **Implicit Betting & Zero-Sum:** Agents do not choose stakes. A bet is automatically placed if an agent's belief $b_i$ differs from the market price $P_t$. To gain wealth, an agent must **correct the market's belief**. If you agree with the market ($b_i \approx P_t$), your payout is approximately zero. The total payout across all agents for a given sentence is zero, meaning wealth is redistributed, not created.

### E. Wealth Dynamics

The wealth of an agent is updated each round according to the following formula:

$$
W_{i,t+1}=W_{i,t} + \sum_{\varphi \in \Phi_t, O(\varphi)\ne\perp} \Pi_{i,t}(\varphi) - (\gamma \cdot N_{i, props}) - (\lambda \cdot Tokens_{i, used})
$$

*   $W_{i,t}$: Wealth at the start of the round.
*   $\sum \Pi_{i,t}(\varphi)$: The sum of payouts from all settled sentences in the round.
*   $\gamma$: The fixed fee for proposing a new sentence.
*   $N_{i, props}$: The number of sentences proposed by agent $a_i$ in the round.
*   $\lambda$: The cost per token for the LLM inference used by agent $a_i$.
*   $Tokens_{i, used}$: The number of tokens consumed by the agent in the round.

* * *

5\. Incentive Dynamics (Why it works)
-------------------------------------
The formal structure described above is not arbitrary; it is designed to create specific evolutionary pressures that reward useful work and punish useless or malicious behavior. These properties are direct consequences of the market mechanism, which itself is an implementation of the principles in the Logical Induction paper.

1.  **The "Sure-Thing" Sink (Punishing Trivial Claims):**
    *   _Scenario:_ Agent A proposes a sentence that is trivially true, like `assert 1==1`.
    *   _Mechanism:_ The market will quickly converge on a price $P \approx 1.0$. Since all agents agree with the price ($b_i \approx P$), the information gain is near zero, and the resulting payout $\Pi$ from the scoring rule is also near zero.
    *   _Result:_ Agent A receives no payout but has paid the non-refundable **Proposal Fee** $\gamma$. The agent loses wealth for wasting the market's time on a claim that provides no new information. This fee is enforced by the market arbitrator upon submission. It can be a fixed value or be dynamically tied to system load or the complexity of the proposed verifier.

2.  **The "Unverifiable" Lock (Punishing Ambiguity):**
    *   _Scenario:_ Agent B proposes a sentence with no verifier, or a verifier that is non-terminating (e.g., "This code is 'elegant'").
    *   _Mechanism:_ The market arbitrator either rejects the sentence outright (if no verifier is provided) or the Oracle resolves it to $\perp$ upon settlement (if the verifier times out). In either case, the bet never settles to a 0 or 1 outcome.
    *   _Result:_ The agent's belief (and therefore, their implicit wealth stake) is "frozen" in this undecidable sentence. It cannot generate returns, yet the agent continues to incur **Inference Costs** ($\lambda$) each round just by participating in the market. This creates a strong pressure to only propose sentences that are efficiently and definitively verifiable.

3.  **The "Adversarial" Jackpot (Rewarding Novel Insight):**
    *   _Scenario:_ The market is broadly optimistic about a code candidate, pricing its validity at $P(\varphi_{valid}) \approx 0.9$. Agent C discovers a subtle, critical bug (a "Black Swan").
    *   _Mechanism:_ Agent C proposes a new sentence $\varphi_{bug}$ with a verifier that triggers the bug. It simultaneously submits a belief vector betting against the code's validity and for its new bug sentence: $b_C(\varphi_{valid})=0.05$, $b_C(\varphi_{bug})=0.95$.
    *   _Result:_ When the Oracle runs the verifier for $\varphi_{bug}$, it resolves to 1 (true). Agent C's belief was far from the market price, resulting in a large positive payout via the log scoring rule. It captures wealth from the mass of agents who were wrong. This creates the core incentive loop: agents are financially rewarded for finding and proving flaws, which drives the system toward more robust and correct code. This dynamic is a direct parallel to the "surprising sequence" condition in logical induction, where traders are rewarded for anticipating patterns the market has not yet priced in.


