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
<!-- good to define induction vs deduction and their roles w/in this system and other LI systems -->
*   **The Incentive:** Agents are incentivized to **accurately predict the output of verifiers**. This creates an environment where agents act as _Architects_ (building and patching robust code) and _Auditors_ (proposing new verifiers to stress-test the market’s assumptions).
*   **Logical Anchoring (The Whale):** To ensure the market respects fundamental logic without using a rigid arbitrator, we introduce a **Deductive Arbitrager** (The Whale). It possesses a wealth balance continuously rebalanced to equal the sum of all other agents. It enforces a "witnessed failure" rule: if a test fails one candidate but passes another, the Whale bets heavily against the failing candidate.
*   **The Result:** The system naturally filters out fragile code and generates useful verifiers (tests).

## 2. Operational Workflow

### Phase A: Initialization (The Bootstrap)

The system begins when the user provides a prompt  $P_{user}$  and a budget $B$. 

1.  **Draft:** The Orchestrator prompts  $N$  agents to generate initial code solutions ( $C_{1},\dots ,C_{N}$ ).
2.  **Initial Assets (Master Goals):** The Orchestrator registers a **Master Goal Sentence** for each solution: $\phi_{G,k} = \text{"Candidate  }k\text{  best satisfies the user's prompt."}$
    *   *Note*: These act as the primary index of confidence for each solution.
    *   *Note*: Because only one candidate can *best* satisfy the prompt, these sentences are mutually exclusive.
3.  **Capital:** Agents (various rollouts of AI coding tools) are initialized with a bankroll of **Compute Credits** ( $W_{i} = B / N$ ). This wealth represents their "computational voting power" or reputation within the system.
3.  **Capital Allocation:**
<!-- explain the role of the whale & deductive agents in general w/in LI -->
    *   **Deductive Whale:** Initialized with 50% of the total market wealth ( $W_{whale}=∑W_{agents}$ ).
<!-- explain the role of indeuctive agents w/in LI - and their specific role w/in this system -->
    *   **Inductive Minnows (LLMs):** Agents (various rollouts of AI coding tools) are initialized with a bankroll of **Compute Credits** ( $W_{i} = B / N$ ).
    *   **The Inference Tax:** To represent the cost of "thinking," agents pay a recurring fee ( $T_{inf}$ ) that decreases their budget over time, ensuring only efficient, accurate traders survive.

### Phase B: Atomic Trading Round

The market operates in discrete rounds where agents privately analyze code, improve their own work, and share findings to update the consensus.

1.  **Observation:** Agents observe the **Market Board**
    - Source code for each candidate
    <!-- terminology for sentence and verifier is not yet defined - its also not clear that in this context - verifier must be quickly and cheaply computable - so basically a unit test - when defining terminology give examples -->
    - Sentences and their verifiers.
    - Optionally, we may or may not expose prices ( $P_{t}$ ) for sentences to agents
<!-- its a little confusing that verifirers are introduced and defined here despits being mentioned eariler flow of infomration is out of order -->
2.  **Inference (Private Sandbox):** Agents write **Verifiers** (tests) to validate candidates and develop **Patches** for their own code.
3.  **The Atomic Action:** Agents submit a **Sealed Envelope** containing three linked actions:
<!-- give examples of verifiers - explain why a verifier that differentiates candiates is the most valuable -->
<!-- link differentiating verifiers to the deductive betting agent and exlpain how that agent rewards differentiating tests -->
    *   **Action A (Propose Verifier):** Introduce new evidence. Proposing a verifier requires a **Proposal Fee**. Proposers gain wealth not by the test itself (which is public), but by being the first to bet on the _implications_ of that test.
<!-- explain how uopdating code (finding bugs in their own code) can enable agents to gain wealth  -->
    *   **Action B (Update Candidate):** Agents may submit a **new version** ( $C_{k,v+1}$ ) to fix bugs they've discovered before auditors can exploit them.
<!-- exxplain this belief vector -->
    *   **Action C (Bet):** Submit a **Belief Vector**  $b$  (probabilities  $0\dots 1$ ).
<!-- explain how the inductive agents (LLMs) and deductive whale calculate their beliefs -->

### Phase C: Settlement

The system resolves the pending logic and redistributes wealth based on empirical results. This phase converts "computational hunches" into concrete market consensus through a deterministic, scaling-aware betting engine.

#### **1\. Execution: The Oracle Run**

The **Arbitrator** executes newly proposed Verifiers in the secure `/tmp/` worktrees.

*   **Logical Anchoring:** Results are binary (**Pass/Fail**). If a test is uncomputable or times out, it is treated as "Undefined" ( $\perp$ ) and no wealth changes hands.
<!-- what is market state json? what is public gallery? -->
*   **Evidence Publishing:** Results are written to the `market_state.json` and the code is snapshotted into the `public_gallery/`.

#### **2\. Belief-to-Bet Conversion (Unleveraged Multi-Asset Allocation)**

To ensure market stability and prevent instant bankruptcy from hallucinations, the Orchestrator translates **Belief Vectors** into a **Fractional Kelly Portfolio**. This model treats the tournament as a collection of independent growth opportunities.

*   **Inductive Agents (Minnows):**
    *   **The Individual Stake:** For every sentence  $\phi _{j}$  in an agent’s sparse vector, the Orchestrator calculates the ideal **Kelly fraction** ( $f_{j\ast }$ ) based on the "Edge vs. Odds":
        $$
        f_{j\ast }=\frac{b_{i,j}-P_{t,j}}{P_{t,j}\left(1-P_{t,j}\right)}
        $$
    *   **The Multi-Asset Scale ( $\kappa$ ):** To remain **unleveraged**, the Orchestrator calculates the total absolute exposure ( $L=∑∣f_{j\ast }∣$ ). It then derives a scaling constant  $\kappa _{i}=\eta /\max \left(1,L\right)$ , where  $\eta$  is a risk-aversion parameter (e.g.,  $0.1$ ). This ensures the total capital at risk never exceeds the agent's available wealth.
    *   **The Sparse Rule:** If an agent fails to report a belief for a sentence, they take **zero position** ( $\kappa _{i,j}=0$ ).
*   **The Deductive Agent (Whale):**
    *   **Standardized Participation:** The Whale is a peer in the betting engine. It possesses a belief vector  $b_{whale}$  and a massive wealth balance  $W_{whale}$ .
    *   **The Witness Trigger:** The Whale updates its beliefs based on the **Arbitrator's** findings. If Candidate  $C_{i}$  fails a test that a witness  $C_{j}$  passed, the Whale sets  $b_{whale,\varphi _{G,i}}=0.0$ .
    *   **The Impact:** Like any other agent, the Whale's influence is scaled by its  $\kappa _{whale}$ . Because it holds 50% of the total wealth, its  $0.0$  belief exerts massive pressure on the equilibrium price, effectively "crushing" failing candidates.

#### **3\. Market Update: Scaling-Weighted Consensus**

The new price  $P_{t+1}$  is the **Market Clearing Price**—the equilibrium point where the total "demand" from all Kelly-betting agents is zero. Because agents use fractional scaling, the price is the centroid of beliefs weighted by **Active Risk** ( $W_{i}\cdot \kappa _{i}$ ):

$$
P_{t+1}\left(\varphi \right)=\frac{∑\left(W_{i,t}\cdot \kappa _{i}\cdot b_{i,\varphi }\right)}{∑\left(W_{i,t}\cdot \kappa _{i}\right)}
$$

> **The Effect:** This ensures that cautious agents (low  $\kappa$ ) or those sitting out (zero  $\kappa$ ) move the price less than confident agents who have committed significant capital to their "alpha."

#### **4\. Payout: Scaled Linearized Redistribution**

Wealth is redistributed based on the **Fractional Log-Scoring Rule**. Since we are using constrained, fractional Kelly betting, the payout is linearized to match the actual capital committed.

$$
\Delta W_{i}=\alpha \cdot W_{i,t}\cdot \kappa _{i}\cdot \left[1_{\varphi }\left(\frac{b_{i}-P_{t}}{P_{t}}\right)+\left(1-1_{\varphi }\right)\left(\frac{P_{t}-b_{i}}{1-P_{t}}\right)\right]
$$

*   **The "Skin in the Game" Match:** This formula represents the wealth change of an agent who only risked a fraction  $\kappa$  of their bankroll. It rewards reducing the market's "surprise" while keeping payouts strictly within the bounds of the agent's committed collateral.
*   **Auditors:** Capture the "spread" between their skeptical belief and the optimistic market price when a bug is proven.
*   **Architects:** Earn a "risk premium" as their price stabilizes toward  $1.0$ .

#### **5\. Rebalance**

After payouts are processed, the system resets for the next tick:

*   **Inference Tax:** The cost of tokens and thinking time is deducted from the agents.

*   **Whale Reset:** The Whale's budget is re-indexed to  $W_{whale}=∑W_{agents}$ , maintaining the logical anchor.

<!-- how are agents w/ no or very low funds cleaned up / liquidated? -->

### Phase D: Iteration & Convergence (Market Settlement)

The cycle resets. The market re-evaluates the candidates against the accumulated suite of verifiers. This process is not infinite; it naturally converges toward a **Market Settlement** due to two specific economic pressures:

1.  **Economic Attrition (The Inference Tax):** Because agents pay a continuous "Tax" for thinking and observing, the total wealth of the speculative pool diminishes over time. Agents who fail to find profitable bugs or useful patches eventually go bankrupt. This reduces "noise" and concentrates the remaining wealth in the hands of the most accurate predictors.
2.  **Information Saturation:** As the code becomes more robust, finding a new, valid bug becomes exponentially harder. Eventually, the cost of discovering a new bug (Inference Cost) exceeds the potential reward from the Whale (Bounty). When agents stop proposing new verifiers because it is no longer profitable, the price stabilizes.
3.  **The Stop Condition:** The Orchestrator halts the loop when the **Market Volatility** drops below a threshold (i.e., prices stop moving despite active trading) or when the collective budget of the Inductive Agents falls below a critical "Liveness" level.

## 3. Incentive Dynamics (Why it works)
This formal structure creates specific evolutionary pressures:
<!-- update the incentive dynamics to reflect the design evolutoin in the section above -->
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

## 4. Formal System Specification

<!-- this needs an update to reflect design changes above -->
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
<!-- similarly this needs an update -->

Wealth is updated based on the **Logarithmic Scoring Rule**. This rule is "strictly proper," meaning an agent maximizes expected wealth *only* by reporting their true subjective probability.

The payout  $\Pi _{i,t}$  for agent  $a_{i}$  given Oracle result  $1_{\varphi }$ :

$$ \Pi _{i,t}\left(\varphi \right)=\alpha \cdot W_{i,t}\cdot \left[1_{\varphi }\ln \left(\frac{b_{i,t}\left(\varphi \right)}{P_{t}\left(\varphi \right)}\right)+\left(1-1_{\varphi }\right)\ln \left(\frac{1-b_{i,t}\left(\varphi \right)}{1-P_{t}\left(\varphi \right)}\right)\right] $$

*   **Implicit Kelly Betting:** This formula is equivalent to agents placing Kelly-optimal bets against the market odds.
*   **Settlement for $\perp$:** If $O(\varphi) = \perp$ (e.g., timeout), $\Pi = 0$. No wealth changes hands. This prevents agents from spamming infinite loops to freeze the market.

### D. Wealth Dynamics

$$ W_{i,t+1}=W_{i,t}+\Pi _{i,t}- \text{Fees} - \text{Costs} $$

*   **Proposal Fees ($\gamma$):** A fixed cost to register a new sentence. Prevents spamming trivial or redundant tests.
*   **Inference Costs ($\lambda$):** A tax on token consumption. Forces agents to be efficient; they must only think if they expect to find a profitable trade (a bug others missed).

## 5. Implementation
## Implementation
<!-- needs better context / intro section - doesn't provide context for oveerall implementaion design before launching into specifics -->
Here is the refined design for the **Adversarial Code Market**. This shifts the complexity from Environment Configuration (Docker) to Market Logic (RAM) and scopes all "messy" data—including verifiers—to the ephemeral tournament folder.

### **1\. Filesystem & Permissions: Purpose & Design**

To keep your main project clean, the Orchestrator creates a **"Disposable Universe"** in `/tmp/`. This folder contains everything specific to this run: the agent's modified code, their private memories, and the test cases (verifiers) they generate to attack each other.

*   **OS-Level User Isolation:** The Orchestrator provisions unique system users (`minnow_1`, `minnow_2`).
*   **The "Open Border" Permissions:** \* **Write Access:** An agent has **Write (`w`)** permission _only_ within its own worktree and session file.
    *   **Read/Execute Access:** Agents are granted **Read (`r`)** and **Execute (`x`)** permissions across the _entire_ tournament directory. This allows them to analyze rival solutions in real-time and execute tests against them.
*   **The Oracle Check:** When Agent A proposes a "Short" on Agent B, the Orchestrator executes Agent A's **Verifier** directly against Agent B's **Worktree**.

```
# 1. THE PERMANENT UNIVERSE (Your Project Root)
/Users/amal/projects/my-app/           (Owner: amal, Perms: 755 [rwxr-xr-x])
│
├── src/                               # Protected source code
├── orchestrator.py                    # THE WARDEN (Runs as sudo/amal)
└── .git/                              # READ-ONLY for all Minnows via ACLs

---------------------------------------------------------------------------

# 2. THE DISPOSABLE UNIVERSE (Created in /tmp/ during run)
/tmp/opencode_market_28a9/             (Owner: amal, Perms: 755 [rwxr-xr-x])
│
├── market_state.json                  (Owner: amal, Perms: 600 [rw-------])
│
├── worktrees/                         (Owner: amal, Perms: 755 [rwxr-xr-x])
│   ├── minnow_1/                      (Owner: minnow_1, Perms: 755 [rwxr-xr-x])
│   │   └── main.py                    <-- minnow_1 can WRITE; Others can READ
│   └── minnow_2/                      (Owner: minnow_2, Perms: 755 [rwxr-xr-x])
│       └── main.py                    <-- minnow_2 can WRITE; Others can READ
│
├── sessions/                          (Owner: amal, Perms: 711 [rwx--x--x])
│   ├── minnow_1.db                    (Owner: minnow_1, Perms: 600 [rw-------])
│   └── minnow_2.db                    (Owner: minnow_2, Perms: 600 [rw-------])
│
└── verifiers/                         (Owner: amal, Perms: 755 [rwxr-xr-x])
    ├── v_8f2a1b/                      # SCOPED EVIDENCE PACKAGES
    │   ├── run.sh                     <-- ALL MINNOWS can EXECUTE
    │   └── test.py                    <-- ALL MINNOWS can READ
    └── v_c3d9e4/
```


### **2\. The Orchestrator (Single-Process Core)**

<!-- make it clear this is all in a single process - everything should be orchestrated via asyncio to prevent blocking -->
The Orchestrator acts as the "Market Exchange." It does not perform the coding itself; it manages the lifecycle of the tournament participants.

*   **Round Management:** It executes a discrete loop (The Tick). Each tick involves syncing file states, collecting "Sealed Moves," and executing verifiers.
*   **Headless SDK Integration:** It spawns OpenCode sessions for each agent. To keep your UI clean, it points each session's `storage_path` to a unique temporary directory in `/tmp/`. This ensures the sub-agents have "private thoughts" that don't leak into your main chat history.
*   **The Shell Contract:** Instead of Docker, it uses `subprocess.run` to execute commands. It expects a binary "Pass/Fail" (Exit 0/1) from any verifier script.

### **3\. The In-Memory Ledger (The Brain)**

Because we are avoiding a database, the entire economic state is a live Python object. This makes the Whale’s reactions instantaneous and avoids disk I/O bottlenecks.

<!-- Explain the data structures used here - provide interface snippets -->
*   **Agent Registry:** A dictionary tracking the wealth and bankruptcy status of every Minnow and the Whale.
*   **Sentence Pricing:** A table of logical claims (e.g., "Feature\_X is bug-free"). Prices fluctuate based on the total wealth "Longing" or "Shorting" that claim.
*   **Inference Tax logic:** A simple function that prunes inefficient agents by deducting a small percentage of wealth every round they fail to provide "Surprise" (new information).

### **4\. Agent Implementation: Parallel "Headless" Sessions**
<!-- re-explain permissions here  -->
The Minnow agents are **not** custom LLM implementations. They are standard `OpenCodeSession` objects, instantiated multiple times in parallel.
<!-- what will we do for agents that get caught in a loop? -->
*   **Reuse of Session Management:** We leverage OpenCode's existing ability to manage token windows, truncate history, and maintain context. We simply override the storage path to our temporary folder (`/tmp/sessions/minnow_1.db`) so they don't overwrite each other.
*   **Market Injection (The Prompt):** Agents don't just "chat." The Orchestrator programmatically injects the **Market Snapshot** into the system prompt at the start of every tick.
    *   _Example Prompt Injection:_
        > "MARKET UPDATE (Round 4): Your wealth is 95.0. Candidate B is currently priced at \$0.80. You previously shorted Candidate B, but the test passed. OBJECTIVE: Analyze Candidate B's new code in `./worktrees/minnow_2` and write a Python test case that breaks it."

This turns the standard "Coding Assistant" into a "Strategic Trader" without rewriting the SDK.

### **5\. The Whale (The Witness Logic)**

The Whale is the "Deductive Anchor" that holds 50% of the initial wealth. Its behavior is strictly logical and reactionary—it never "guesses."

<!-- where dose the whale live? I think we should just have it eecute inprocess w/in the markte arbitrator process -->
**The Logic: The Witness Requirement** The Whale does not punish code merely for failing. It punishes code for being **inferior to a proven alternative.**

1.  **Observation:** The Whale watches the Oracle run a verifier test ( $T$ ) against two candidates,  $C_{i}$  (Agent A's code) and  $C_{j}$  (Agent B's code).
2.  **The Trigger:**
    *   If  $C_{i}$  fails test  $T$ ...
    *   **AND**  $C_{j}$  passes test  $T$  (The "Witness")...
3.  **The Crush:** Only then does the Whale mobilize its 50% wealth to **Short** the sentence  $\phi _{G,i}$  ("Candidate  $i$  is correct") toward  $0$ .

**Why this matters:** This ensures the market is **constructive**. You cannot profit by writing an impossible test that _everyone_ fails. You can only profit by writing a test that _you pass_ and _your opponent fails_. This forces the agents to actually fix bugs, not just find them.

### **6\. The Interface Layer (Code Structure)**

To keep the implementation modular, we define three primary interfaces. You can swap the "under the hood" execution from Native to Docker later by simply changing the logic inside these classes.

**A. The Market State Interface** Manages the "Gold Standard" of who owns what.
<!-- what about sentences? where are they stored? -->
<!-- what is data format for ledger -->
<!-- explain that the market operates on ticks - if any agent misses a  -->
<!-- how is the whale implemented? -->
```
class MarketState:
    def apply_tax(self, rate: float): ...
    def update_price(self, sentence_id: str, new_bet: float): ...
    def settle_truth(self, sentence_id: str, result: bool): ...
    def get_consensus(self) -> dict: ... # Returns current "best" code versions
```

<!-- imprecise description of a verifier - also need to handle uncomputable/non-terminating verifiers  -->
**B. The Verifier Interface** Manages the interaction between the market and the physical disk.

```
class Verifier:
    def __init__(self, test_script: str, cmd: str): ...
    def execute(self, target_worktree: str) -> bool:
        # Returns True for Exit 0, False for Exit 1+
        ...
```

**C. The Agent Wrapper** The bridge between the OpenCode "Brain" and our tournament.


<!-- provide a snippet describing the structre of Move data typoe here -->
<!-- how do we extract belief vector from agent? - what if agent fails to report a belief for a sentence? -->
<!-- how do we handle agents that dont respond w/in some amount of time? -->
```
class AdversarialAgent:
    def __init__(self, agent_id: str, worktree_path: str): ...
    async def get_next_move(self, market_snapshot: dict) -> Move:
        # Returns a "Sealed Envelope" containing Code + Bets
        ...
```

