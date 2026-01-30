# OpenCode Logical Induction Market
==============================================================

**Context:** A resource-competitive software engineering tournament implemented within the `OpenCode` terminal environment. 

**Theoretical Foundation:** Computable approximation of _Logical Induction_ [Garrabrant et al., 2016](https://arxiv.org/abs/1609.03543).

<!-- this is pretty dense and vague - what is goalB - what is test A etcc... -->
**Theoretical Motivation:**
This system is motivated by the _Logical Induction Criterion_, which states that a market of bounded traders will eventually assign probabilities to logical statements that respect the rules of deduction. In software engineering, this means the market will converge on the realization that "If Test A fails, Goal B cannot be True," without needing a human to explicitly program that dependency. The market aggregates "computational hunches" from diverse agents into a coherent probability distribution over code correctness.

* * *

## 1. High-Level Concept & Motivation

### Core Problem

Current Agentic coding systems (like Devin or standard RAG loops) typically rely on a single model checking itself ("Self-Reflection"). This is fragile; models often hallucinate that their own broken code works. Parallel sampling ("Best-of-N") generates many options but lacks a rigorous, automated way to select the winner without expensive human review.

### The Solution: A Logical Induction Market (Truth via Consensus)

<!-- explain that we are looking not for code correctness but some unverifiable property of code "quality" - how well does it address the prompt - how "correct" is it - etc...  -->
We replace the traditional "Judge" with a **Logical Induction Market**. This approach treats code correctness as a dynamic market consensus that converges through rigorous verification and continuous economic alignment.

*   **The Foundation:** This framework treats "truth" as a state where no computationally bounded trader can find a "surprise" (an overlooked bug).
<!-- this is not really true - agents are incentivized to fix bugs in their code and findd bugs in other pieces of code - explain how verifiable bugs can be linked to non veriable goals like "how well does this candiate address the prompt" -->
*   **The Incentive:** Agents are incentivized to **accurately predict the output of verifiers**. This creates a collaborative ecosystem where agents act as _Architects_ (building and patching robust code) and _Auditors_ (proposing new verifiers to stress-test the market’s assumptions).
*   **Logical Anchoring (The Whale):** To ensure the market respects fundamental logic without using a rigid arbitrator, we introduce a **Deductive Agent** (The Whale). It possesses a wealth balance continuously rebalanced to equal the sum of all other agents. It enforces a "witnessed failure" rule: if a test fails one candidate but passes another, the Whale bets heavily against the failing candidate.
*   **The Result:** The system naturally filters out fragile code and generates useful verifiers (tests).

## 2. Operational Workflow

### Phase A: Initialization (The Bootstrap)

The system begins when the user provides a prompt  $P_{user}$  and a budget $B$. 

1.  **Draft:** The Orchestrator prompts  $N$  agents to generate initial code solutions ( $C_{1},\dots ,C_{N}$ ).
2.  **Initial Assets (Master Goals):** The Orchestrator registers a **Master Goal Sentence** for each solution: $\phi_{G,k} = \text{"Candidate  }k\text{  satisfies the user's prompt."}$
    *   _Note:_ These act as the primary index of confidence for each solution.
3.  **Capital:** Agents (various rollouts of AI coding tools) are initialized with a bankroll of **Compute Credits** ( $W_{i} = B / N$ ). This wealth represents their "computational voting power" or reputation within the system.
3.  **Capital Allocation:**
    *   **Deductive Whale:** Initialized with 50% of the total market wealth ( $W_{whale}=∑W_{agents}$ ).
    *   **Inductive Minnows (LLMs):** Agents (various rollouts of AI coding tools) are initialized with a bankroll of **Compute Credits** ( $W_{i} = B / N$ ). 
    *   **The Inference Tax:** To represent the cost of "thinking," agents pay a recurring fee ( $T_{inf}$ ) that decreases their budget over time, ensuring only efficient, accurate traders survive. Note this also decreases the budget allocated to the deductive trader.

### Phase B: Atomic Trading Round

The market operates in discrete rounds where agents privately analyze code, improve their own work, and share findings to update the consensus.

1.  **Observation:** Agents observe the **Market Board**
    - Source code for each candidate
    <!-- terminology for sentence and verifier is not yet defined - its also not clear that in this context - verifier must be quickly and cheaply computable - so basically a unit test - when defining terminology give examples -->
    - Sentences and their verifiers.
    - Optionally, we may or may not expose prices ( $P_{t}$ ) for sentences to agents
<!-- its a little confusing that verifirers are introduced here despits being mentioned eariler -->
2.  **Inference (Private Sandbox):** Agents use credits to run private simulations. They write **Verifiers** (tests) to validate candidates and develop **Patches** for their own code.
3.  **The Atomic Action:** Agents submit a **Sealed Envelope** containing three linked actions:
<!-- give examples of verifiers - explain why a verifier that differentiates candiates is the most valuable -->
<!-- link differentiating verifiers to the deductive betting agent and exlpain how that agent rewards differentiating tests -->
    *   **Action A (Propose Verifier):** Introduce new evidence. Proposing a verifier requires a **Proposal Fee**. Proposers gain wealth not by the test itself (which is public), but by being the first to bet on the _implications_ of that test.
<!-- explain how uopdating code (finding bugs in their own code) can enable agents to gain wealth  -->
    *   **Action B (Update Candidate):** Agents may submit a **new version** ( $C_{k,v+1}$ ) to fix bugs they've discovered before auditors can exploit them.
<!-- exxplain this belief vector -->
    *   **Action C (Bet):** Submit a **Belief Vector**  $b$  (probabilities  $0\dots 1$ ).


### Phase C: Settlement (The Oracle)

The system resolves the pending logic and redistributes wealth based on empirical results.

1.  **Execution:** The **Arbitrator** runs newly proposed Verifiers in a secure sandbox.
2.  **The Whale’s Move:** The Whale observes the results. If a candidate  $C_{i}$  fails a test that a "witness"  $C_{j}$  passed, the Whale applies its massive wealth to short  $\varphi _{G,i}$  toward  $0$ .
<!-- need to explain how belief vector is coverted to bets (kelly betting) - explain how these bets resolve into this market update -->
3.  **Market Update:** The price  $P_{t+1}$  is calculated as the wealth-weighted average of all beliefs:
    $$
    P_{t+1}\left(\varphi \right)=\frac{∑\left(W_{i}\cdot b_{i,\varphi }\right)}{∑W_{i}}
    $$
4.  **Payout:**
    *   **Auditors** who correctly predicted failures (via shorts) gain wealth from the Whale and failing Architects.
    *   **Architects** who proactively patched and bet on their success gain credits as the market stabilizes.
5.  **Rebalance:** The Whale's budget is reset to match the total current wealth of all agents, maintaining the logical anchor for the next tick.

### Phase D: Iteration & Convergence (Market Settlement)

The cycle resets. The market re-evaluates the candidates against the accumulated suite of verifiers. This process is not infinite; it naturally converges toward a **Market Settlement** due to two specific economic pressures:

1.  **Economic Attrition (The Inference Tax):** Because agents pay a continuous "Tax" for thinking and observing, the total wealth of the speculative pool diminishes over time. Agents who fail to find profitable bugs or useful patches eventually go bankrupt. This reduces "noise" and concentrates the remaining wealth in the hands of the most accurate predictors.
2.  **Information Saturation:** As the code becomes more robust, finding a new, valid bug becomes exponentially harder. Eventually, the cost of discovering a new bug (Inference Cost) exceeds the potential reward from the Whale (Bounty). When agents stop proposing new verifiers because it is no longer profitable, the price stabilizes.
3.  **The Stop Condition:** The Orchestrator halts the loop when the **Market Volatility** drops below a threshold (i.e., prices stop moving despite active trading) or when the collective budget of the Inductive Agents falls below a critical "Liveness" level.

## Implementation
<!-- I think this lacks some specificity about how we might actually implement this in opencode -->

### orchestration in opencode
<!-- this needs to be explained -->

### Inductive agents as a OpenCode Session Trace

In this implementation, an agent is an **`OpenCode` Agent** (a specific configuration of the `OpenCode` runner).

*   **Identity:** Each agent persists its "Chain of Thought" history, allowing for multi-step reasoning across market rounds.
*   **The Toolset:**
    *   `read_market_state()`: View prices, active sentences, and candidate code.
    <!-- i think this tool is already part of the opencode framework - we should not reimplemetn this -->
    *   `run_local_tool(cmd)`: Execute private checks (e.g., `python -m py_compile candidate.py`) to inform beliefs.
    *   `propose_sentence(description, verifier_code)`: Register new claims.
        *   *Example:* `propose_sentence("Fails on null input", "assert my_func(None) is not None")`
    *   `submit_belief(sentence_id, probability)`: Trade on existing claims.

> **Example Trace:**
> 
> *   **Thought:** "The Architect's code for the parser looks correct, but it uses a deprecated library."
> *   **Local Action:** `run_local_tool("pip check candidate_a.py")`  $\to$  `Result: Dependency Error`.
> *   **Proposal:** `propose_sentence("Candidate_A fails dependency check", verifier="import candidate_a; ...")`.
> *   **Trade:** `submit_belief("s_goal", 0.1)` (Shorting the goal) and `submit_belief("s_dep_check", 0.99)` (Longing the failure).
>     

### Deductive agent
<!-- Need thsi to be explained -->

### market arbitrator
<!-- also need this to be explained -->


## 4. Formal System Specification

The market is defined as a discrete-time dynamical system  $\Sigma =\left⟨A,\Phi ,W,O\right⟩$ .

*   ** $A$ **: The set of  $m$  Agents.
*   ** $\Phi _{t}$ **: The set of active Logical Sentences at round  $t$ .
*   ** $W_{t}\in R_{\ge 0m}$ **: The Wealth Vector (Compute Credits).
*   ** $O:\Phi \to \{0,1,\perp\}$ **: The Oracle function. $\perp$ denotes "Undefined" (e.g., timeout, resource exhaustion, or intrinsically unverifiable).

### A. The Assets: Sentences & Oracles

Every tradeable asset is a Sentence $\varphi$ paired with a Verifier $V_\varphi$.

*   **Verifiable Sentences ( $\varphi _{test}$ ):** Possess a computable verifier function  $V_{\varphi }$ . The Oracle  $O\left(\varphi \right)$  is the return value of  $Exec\left(V_{\varphi }\right)$ .
    *   *Implementation:* A Python script or Pytest case.
*   **Unverifiable Sentences ( $\varphi _{goal}$ ):** Do not possess a direct verifier (e.g., "This code is 'good'").  $O\left(\varphi \right)=\perp$  (Undefined) until the end of the tournament (or settled by human).
    *   *Market Logic:* Agents trade $\varphi_{goal}$ based on its correlation with $\varphi_{test}$. If $\varphi_{test}$ fails, logically $\varphi_{goal}$ should drop.

### B. Consensus Price ( $P_{t}$ )

The Market Price is the **Wealth-Weighted Centroid** of agent beliefs. Let  $b_{i,t}$  be the belief vector of agent  $a_{i}$ .

$$ P_{t}\left(\varphi \right)=\frac{\sum_{i=1}^{m} W_{i,t}\cdot b_{i,t}\left(\varphi \right)}{\sum_{i=1}^{m} W_{i,t}} $$

> **Interpretation:** A "Rich" agent (one with high historical accuracy) moves the market price significantly more than a "Poor" agent. This aligns with the Logical Induction formalism where the market probability dominates any bounded trader.

### C. The Payout (Logarithmic Scoring)

Wealth is updated based on the **Logarithmic Scoring Rule**. This rule is "strictly proper," meaning an agent maximizes expected wealth *only* by reporting their true subjective probability.

The payout  $\Pi _{i,t}$  for agent  $a_{i}$  given Oracle result  $1_{\varphi }$ :

$$ \Pi _{i,t}\left(\varphi \right)=\alpha \cdot W_{i,t}\cdot \left[1_{\varphi }\ln \left(\frac{b_{i,t}\left(\varphi \right)}{P_{t}\left(\varphi \right)}\right)+\left(1-1_{\varphi }\right)\ln \left(\frac{1-b_{i,t}\left(\varphi \right)}{1-P_{t}\left(\varphi \right)}\right)\right] $$

*   **Implicit Kelly Betting:** This formula is equivalent to agents placing Kelly-optimal bets against the market odds.
*   **Settlement for $\perp$:** If $O(\varphi) = \perp$ (e.g., timeout), $\Pi = 0$. No wealth changes hands. This prevents agents from spamming infinite loops to freeze the market.

### D. Wealth Dynamics

$$ W_{i,t+1}=W_{i,t}+\Pi _{i,t}- \text{Fees} - \text{Costs} $$

*   **Proposal Fees ($\gamma$):** A fixed cost to register a new sentence. Prevents spamming trivial or redundant tests.
*   **Inference Costs ($\lambda$):** A tax on token consumption. Forces agents to be efficient; they must only think if they expect to find a profitable trade (a bug others missed).

## 5. Incentive Dynamics (Why it works)
This formal structure creates specific evolutionary pressures:

1.  **The "Sure-Thing" Sink:**
    *   _Scenario:_ Agent A proposes `assert 1==1`.
    *   _Outcome:_ Everyone agrees ( $b_{i}\approx 1.0$ ). The price  $P\approx 1.0$ . Payout is $\approx 0$.
    *   _Result:_ Agent A loses money (the Proposal Fee  $\gamma$ ) for wasting the market's time.
2.  **The "Unverifiable" Lock:**
    *   _Scenario:_ Agent B proposes "Code is elegant" (No Verifier).
    *   _Outcome:_  $O\left(\varphi \right)=\perp$ . The bet never settles.
    *   _Result:_ Agent B's wealth is effectively "frozen" in this belief, unable to generate returns, while their Inference Costs drain them.
3.  **The "Adversarial" Jackpot:**
    *   _Scenario:_ The market is optimistic ( $P\approx 0.9$ ). Agent C finds a "Black Swan" bug and bets  $b_{C}=0.05$ .
    *   _Outcome:_ The test runs and fails ( $1=0$ ).
    *   _Result:_ Agent C captures massive wealth from the optimistic agents. This incentivizes deep, creative testing over superficial agreement.