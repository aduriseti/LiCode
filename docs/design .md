# OpenCode Logical Induction Market
==============================================================

**Context:** A resource-competitive software engineering tournament implemented within the `OpenCode` terminal environment. 

**Theoretical Foundation:** Computable approximation of _Logical Induction_ [Garrabrant et al., 2016](https://arxiv.org/abs/1609.03543).

**Theoretical Motivation:**
This system is motivated by the _Logical Induction Criterion_ [Garrabrant et al., 2016], which proves that a market of bounded traders will eventually assign probabilities to logical statements that respect the rules of deduction. 

*Example:* Consider a sorting algorithm. 
- **Sentence G (Goal):** "The function `sort(list)` correctly sorts any input."
- **Sentence T (Test):** "The function returns `[1, 2]` when input is `[2, 1]`."
- **Logic:** If $T$ is false (test fails), then $G$ must be false.

In a Logical Induction market, agents who realize this implication first can profit by "shorting" $G$ as soon as they see $T$ fail, even if the system explicitly rewards $G$. This forces the market price of $G$ to drop, reflecting the code's broken state without a human arbiter manually flagging the bug.

* * *

## 1. High-Level Concept & Motivation

### Core Problem

Current Agentic coding systems (like Devin or standard RAG loops) typically rely on a single model checking itself ("Self-Reflection"). This is fragile; models often hallucinate that their own broken code works. Parallel sampling ("Best-of-N") generates many options but lacks a rigorous, automated way to select the winner without expensive human review.

### The Solution: A Logical Induction Market (Truth via Consensus)

We replace the traditional "Judge" with a **Logical Induction Market**. 

**What is "Truth" here?**
We represent code quality as a probability, not a boolean. "Truth" is not merely "compiles and runs," but a measure of **Market Confidence** that a candidate satisfies the user's prompt. This allows us to quantify soft goals (e.g., "Is this code clean?") alongside hard goals (e.g., "Does it pass test X?").

*   **The Foundation:** The market converges to a state where no computationally bounded trader can find a profitable "surprise." If a bug exists that no agent can find (given their compute budget), the market treats the code as correct *for now*.
*   **The Incentive:** Agents are incentivized to link **Verifiable Facts** (Test A passed/failed) to **Unverifiable Goals** (Candidate X is good).
    *   If Agent A spots a bug in Candidate B, they don't just report it; they **bet against** Candidate B's goal sentence.
    *   When the test runs and fails, the price of Candidate B crashes. Agent A profits from the "spread" between the market's optimism and the cold hard reality of the failed test.
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
    - **Source Code:** The current version of each candidate solution.
    - **Asset List (Sentences):** A list of active statements about the code (e.g., "Candidate 1 passes Test X").
    - **Price History:** The current market probability ($P_t$) for each sentence.
2.  **Inference (Private Sandbox):** Agents use credits to run private simulations. They write **Verifiers** (fast, cheap unit tests) to validate candidates and develop **Patches** for their own code.
3.  **The Atomic Action:** Agents submit a **Sealed Envelope** containing three linked actions:
    *   **Action A (Propose Verifier):** Introduce new evidence in the form of a unit test.
        *   *Example:* `test_sort_empty_list.py`
        *   *Value:* The most valuable verifiers are **Differentiators**—tests that pass one candidate but fail another. These trigger the Whale (Deductive Agent) to bet heavily against the loser, allowing the proposer (who bet early) to capture significant wealth.
    *   **Action B (Update Candidate):** Agents may submit a **new version** ( $C_{k,v+1}$ ) to fix bugs.
        *   *Incentive:* Fixing a bug allows the agent to bet *Long* (1.0) on their own candidate with certainty. If they don't fix it, an opponent will find the bug, bet *Short*, and drain their wealth.
    *   **Action C (Bet):** Submit a **Belief Vector**  $b$ .
        *   *Definition:* A map of `{ Sentence_ID: Probability }`. e.g., `{ "Cand1_is_Good": 0.05, "Test_Sort_Empty": 0.99 }`.
        *   *Source:* 
            *   **Inductive Agents (LLMs):** Derive beliefs from their internal logic and private test results ("I ran the test and it failed, so I bet 0.0").
            *   **Deductive Whale:** Derives beliefs from witnessed contradictions ("Cand 1 failed a test that Cand 2 passed, so Cand 1 must be False").

### Phase C: Settlement

The system resolves the pending logic and redistributes wealth based on empirical results. This phase converts "computational hunches" into concrete market consensus through a deterministic, scaling-aware betting engine.

* * *

#### **1\. Belief-to-Bet Conversion (Unleveraged Multi-Asset Allocation)**

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

* * *

#### **2\. Execution: The Oracle Run**

The **Arbitrator** executes newly proposed Verifiers in the secure `/tmp/` worktrees.

*   **Logical Anchoring:** Results are binary (**Pass/Fail**). If a test is uncomputable or times out, it is treated as "Undefined" ( $\perp$ ) and no wealth changes hands.
*   **Evidence Publishing:** Results are written to the `market_state.json` and the code is snapshotted into the `public_gallery/`.

* * *

#### **3\. Market Update: Scaling-Weighted Consensus**

The new price  $P_{t+1}$  is the **Market Clearing Price**—the equilibrium point where the total "demand" from all Kelly-betting agents is zero. Because agents use fractional scaling, the price is the centroid of beliefs weighted by **Active Risk** ( $W_{i}\cdot \kappa _{i}$ ):

$$
P_{t+1}\left(\varphi \right)=\frac{∑\left(W_{i,t}\cdot \kappa _{i}\cdot b_{i,\varphi }\right)}{∑\left(W_{i,t}\cdot \kappa _{i}\right)}
$$

> **The Effect:** This ensures that cautious agents (low  $\kappa$ ) or those sitting out (zero  $\kappa$ ) move the price less than confident agents who have committed significant capital to their "alpha."

* * *

#### **4\. Payout: Scaled Linearized Redistribution**

Wealth is redistributed based on the **Fractional Log-Scoring Rule**. Since we are using constrained, fractional Kelly betting, the payout is linearized to match the actual capital committed.

$$
\Delta W_{i}=\alpha \cdot W_{i,t}\cdot \kappa _{i}\cdot \left[1_{\varphi }\left(\frac{b_{i}-P_{t}}{P_{t}}\right)+\left(1-1_{\varphi }\right)\left(\frac{P_{t}-b_{i}}{1-P_{t}}\right)\right]
$$

*   **The "Skin in the Game" Match:** This formula represents the wealth change of an agent who only risked a fraction  $\kappa$  of their bankroll. It rewards reducing the market's "surprise" while keeping payouts strictly within the bounds of the agent's committed collateral.
*   **Auditors:** Capture the "spread" between their skeptical belief and the optimistic market price when a bug is proven.
*   **Architects:** Earn a "risk premium" as their price stabilizes toward  $1.0$ .

* * *

#### **5\. Rebalance**

After payouts are processed, the system resets for the next tick:

*   **Inference Tax:** The cost of tokens and thinking time is deducted from the agents.

*   **Whale Reset:** The Whale's budget is re-indexed to  $W_{whale}=∑W_{agents}$ , maintaining the logical anchor.
*   **Liquidation:** Agents whose wealth falls below a critical threshold (e.g., < 1% of initial stake) are marked as **Bankrupt**. They are removed from the active loop to conserve system compute resources.


### Phase D: Iteration & Convergence (Market Settlement)

The cycle resets. The market re-evaluates the candidates against the accumulated suite of verifiers. This process is not infinite; it naturally converges toward a **Market Settlement** due to two specific economic pressures:

1.  **Economic Attrition (The Inference Tax):** Because agents pay a continuous "Tax" for thinking and observing, the total wealth of the speculative pool diminishes over time. Agents who fail to find profitable bugs or useful patches eventually go bankrupt. This reduces "noise" and concentrates the remaining wealth in the hands of the most accurate predictors.
2.  **Information Saturation:** As the code becomes more robust, finding a new, valid bug becomes exponentially harder. Eventually, the cost of discovering a new bug (Inference Cost) exceeds the potential reward from the Whale (Bounty). When agents stop proposing new verifiers because it is no longer profitable, the price stabilizes.
3.  **The Stop Condition:** The Orchestrator halts the loop when the **Market Volatility** drops below a threshold (i.e., prices stop moving despite active trading) or when the collective budget of the Inductive Agents falls below a critical "Liveness" level.

## 3. Incentive Dynamics (Why it works)
This formal structure creates specific evolutionary pressures:

1.  **The "Sure-Thing" Sink:**
    *   _Scenario:_ Agent A proposes `assert 1==1`.
    *   _Outcome:_ Everyone agrees ( $b_{i}\approx 1.0$ ). The price  $P\approx 1.0$ . Payout is $\approx 0$.
    *   _Result:_ Agent A loses money (the Proposal Fee  $\gamma$ ) for wasting the market's time.
2.  **The "Unverifiable" Lock:**
    *   _Scenario:_ Agent B proposes "Code is elegant" (No Verifier).
    *   _Outcome:_  $O\left(\varphi \right)=\perp$ . The bet never settles.
    *   _Result:_ Agent B's wealth is effectively "frozen" in this belief, unable to generate returns, while their Inference Costs drain them.
3.  **The "Adversarial" Jackpot (Witnessed Failure):**
    *   _Scenario:_ The market is optimistic ( $P\approx 0.9$ ) about Candidate X. Agent C finds a bug that Candidate Y avoids.
    *   _Action:_ Agent C bets Short on X ($b_C=0.05$) and Long on Y, then submits the test.
    *   _Outcome:_ Test runs. X fails. Y passes. The Whale sees the Witness and sets $b_{whale,X}=0.0$.
    *   _Result:_ The price of X crashes. Agent C captures massive wealth from the optimistic agents. This incentivizes deep, creative testing over superficial agreement.

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

## 5. Implementation

### Overview
The system is designed as a **Single-Process Orchestrator** managing a "Disposable Universe" of files and sub-processes. 
- **Concurrency:** Uses `asyncio` to manage multiple "Headless" agent sessions and non-blocking I/O (verifiers).
- **Isolation:** Relies on OS-level file permissions and temporary directories rather than heavy Docker containers for this prototype.
- **State:** The entire economic ledger lives in-memory (Python objects) for speed, with periodic JSON snapshots to disk for recovery/analysis.

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

The Orchestrator acts as the "Market Exchange" and runs as a single Python process using `asyncio` event loops. It does not perform the coding itself; it manages the lifecycle of the tournament participants.

*   **Round Management:** It executes a discrete loop (The Tick). Each tick involves syncing file states, collecting "Sealed Moves," and executing verifiers.
*   **Headless SDK Integration:** It spawns OpenCode sessions for each agent. To keep your UI clean, it points each session's `storage_path` to a unique temporary directory in `/tmp/`. This ensures the sub-agents have "private thoughts" that don't leak into your main chat history.
*   **The Shell Contract:** Instead of Docker, it uses `subprocess.run` to execute commands. It expects a binary "Pass/Fail" (Exit 0/1) from any verifier script.

### **3\. The In-Memory Ledger (The Brain)**

Because we are avoiding a database, the entire economic state is a live Python object. This makes the Whale’s reactions instantaneous and avoids disk I/O bottlenecks.

**Core Data Structures:**
*   **Agent Registry:** `Dict[AgentID, AgentState]`
    *   `AgentState = { "wealth": float, "is_bankrupt": bool }`
*   **Sentence Board:** `Dict[SentenceID, SentenceData]`
    *   `SentenceData = { "text": str, "verifier_path": Optional[str], "current_price": float, "history": List[float] }`
*   **Order Book:** `Dict[RoundID, List[Bet]]`
    *   `Bet = { "agent_id": str, "sentence_id": str, "belief": float, "stake": float }`

### **4\. Agent Implementation: Parallel "Headless" Sessions**

The Minnow agents are **not** custom LLM implementations. They are standard `OpenCodeSession` objects, instantiated multiple times in parallel.

*   **Reuse of Session Management:** We leverage OpenCode's existing ability to manage token windows, truncate history, and maintain context. We simply override the storage path to our temporary folder (`/tmp/sessions/minnow_1.db`) so they don't overwrite each other.
*   **Market Injection (The Prompt):** Agents don't just "chat." The Orchestrator programmatically injects the **Market Snapshot** into the system prompt at the start of every tick.
    *   _Example Prompt Injection:_
        > "MARKET UPDATE (Round 4): Your wealth is 95.0. Candidate B is currently priced at \$0.80. You previously shorted Candidate B, but the test passed. OBJECTIVE: Analyze Candidate B's new code in `./worktrees/minnow_2` and write a Python test case that breaks it."

This turns the standard "Coding Assistant" into a "Strategic Trader" without rewriting the SDK.

### **5\. The Whale (The Witness Logic)**

The Whale is the "Deductive Anchor" that holds 50% of the initial wealth. Its behavior is strictly logical and reactionary—it never "guesses."

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
*   **Sentences:** Stored in `self.sentences` (Dict).
*   **Ledger:** Stored in `self.agents` (Dict).
*   **Tick System:** The market operates on discrete `ticks`. If an agent misses a tick (times out), their previous beliefs are carried forward (Passive Hold) or they are forced to "sit out" (0 risk) depending on config.
*   **The Whale:** Implemented as a specialized method `_calculate_whale_bets()` called at the end of every tick before price settlement.

```python
class MarketState:
    def apply_tax(self, rate: float): ...
    def update_price(self, sentence_id: str, new_bet: float): ...
    def settle_truth(self, sentence_id: str, result: bool): ...
    def get_consensus(self) -> dict: ... # Returns current "best" code versions
```

**B. The Verifier Interface** Manages the interaction between the market and the physical disk.
*   **Timeout/Error Handling:** If `execute()` times out or crashes, it returns `Result.UNDEFINED` ($\perp$), ensuring no wealth transfer occurs for bad tests.

```python
class Verifier:
    def __init__(self, test_script: str, cmd: str): ...
    def execute(self, target_worktree: str) -> bool:
        # Returns True for Exit 0, False for Exit 1+
        ...
```

**C. The Agent Wrapper** The bridge between the OpenCode "Brain" and our tournament.

```python
@dataclass
class Move:
    proposed_verifier: Optional[str]  # Path to new test or None
    updated_code_path: Optional[str] # Path to new code or None
    belief_vector: Dict[str, float]   # { "Sentence_ID": 0.0-1.0 }

class AdversarialAgent:
    def __init__(self, agent_id: str, worktree_path: str): ...
    
    async def get_next_move(self, market_snapshot: dict) -> Move:
        # 1. Inject market_snapshot into Prompt
        # 2. Await LLM response (JSON mode)
        # 3. Parse JSON to Move object
        # 4. Handle Timeout: If > 30s, return empty Move (Fold)
        ...
```
