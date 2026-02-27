# OpenCode Logical Induction Market

**Context:** A resource-competitive software engineering tournament implemented within the `OpenCode` terminal environment.

**Theoretical Foundation:** Computable approximation of _Logical Induction_ [Garrabrant et al., 2016](https://arxiv.org/abs/1609.03543), implemented using a Logarithmic Market Scoring Rule (LMSR) mechanism.

**Theoretical Motivation:**
This system is motivated by the _Logical Induction Criterion_, which states that a market of bounded traders will eventually assign probabilities to logical statements that respect the rules of deduction. In software engineering, this means the market will converge on realizations like "If Test A fails on Candidate B, then B cannot be the best solution," without needing a human to explicitly program that dependency. The market aggregates "computational hunches" from diverse agents into a coherent probability distribution over code quality.

* * *

## 1. High-Level Concept & Motivation

### Core Problem

Current agentic coding systems (like Devin or standard RAG loops) typically rely on a single model checking itself ("Self-Reflection"). This is fragile; models often hallucinate that their own broken code works. Parallel sampling ("Best-of-N") generates many options but lacks a rigorous, automated way to select the winner without expensive human review.

### The Solution: A Logical Induction Market (Truth via Consensus)

We replace the traditional "Judge" with a **Logical Induction Market**. This approach treats code quality assessment as a dynamic market consensus that converges through rigorous verification and continuous economic alignment.

**Key Insight:** We seek to evaluate an *unverifiable* property—how well code satisfies the user's prompt. Since this cannot be directly tested, we create a market where agents bet on both:
1. **Verifiable properties**: Test outcomes (decidable via execution)
2. **Unverifiable properties**: Code quality, prompt satisfaction (emergent from market consensus)

The market links these through economic incentives: agents who correctly predict test outcomes gain wealth, which increases their influence on quality assessments.

**Roles of Deduction vs. Induction:**
- **Deduction** (The Whale): Enforces logical consequences of observed facts. If test T fails on candidate C, then C cannot be "best."
- **Induction** (LLM Agents): Search for patterns, propose hypotheses about code behavior, predict test outcomes based on code analysis.

### Market Participants

| Role | Agent Type | Function | Incentive | Capital |
|------|-----------|----------|-----------|---------|
| **Inductive Agents (Sharks)** | LLM-based traders | Search for bugs, propose tests, predict outcomes, improve code | Gain wealth by accurate predictions | $W_i = B/N$ each |
| **Deductive Agent (Whale)** | Algorithmic market maker | Provides liquidity, enforces logical consequences | Not profit-seeking; maintains market structure | $W_{whale} = B$ (fixed) |
| **Orchestrator** | Neutral arbiter | Runs oracles, executes trades, enforces rules | Not a participant; executes deterministic protocol | N/A |

**System Wealth:**
- Total initial wealth: $2B$ (agents + Whale)
- Total wealth decreases over time due to inference tax
- Guarantees convergence: wealth → 0 as rounds → ∞

* * *

## 2. Operational Workflow

### Phase A: Initialization (The Bootstrap)

The system begins when the user provides a prompt $P_{user}$ and a budget $B$.

1. **Draft:** The Orchestrator prompts $N$ agents to generate initial code solutions ($C_{1},\dots ,C_{N}$).

2. **Initial Assets (Master Goals):** The Orchestrator registers a **Master Goal Sentence** for each solution:
   $$\phi_{G,k} = \text{"Candidate }k\text{ best satisfies the user's prompt."}$$
   
   *Note*: These sentences are mutually exclusive (only one can be "best"), though the market mechanism does not enforce $\sum P(\phi_{G,k}) = 1.0$. Prices are interpreted as market credences rather than formal probabilities.

3.  **Capital Allocation:**
    - **Inductive Sharks (LLM Agents):** Each initialized with $W_{i} = B / N$ compute credits
    - **Deductive Whale (Market Maker):** Initialized with $W_{whale} = \sum_{i} W_{i} = B$
    - **Total System Wealth:** $2B$ (conserved throughout)

4. **LMSR Market Initialization:** For each sentence $\phi$, create an LMSR market with:
   
   **Dynamic Liquidity Parameter:**
   $$b_t = \max\left(b_{min}, \frac{0.5 \cdot W_{whale,t}}{M_{active,t} \cdot \ln(2)}\right)$$
   
   where:
   - $W_{whale,t}$: Whale's current wealth
   - $M_{active,t}$: Number of active markets at round $t$
   - $b_{min} = B/200$: Minimum liquidity floor
   - $\ln(2) \approx 0.693$
   
   **Purpose:** This ensures the Whale cannot lose more than 50% of its wealth in any single round while maintaining minimum market liquidity.
   
   **Market Initialization:**
   - Initial shares: $q_{yes} = 0, q_{no} = 0$ (neutral prior)
   - Initial price: $P(\phi) = 0.5$

5. **The Inference Tax:** Agents pay a recurring fee ($T_{inf}$) each round, representing computational cost. This ensures only accurate traders survive long-term.

### Phase B: Atomic Trading Round

The market operates in discrete, synchronous rounds where agents privately analyze code and submit actions simultaneously.

#### **1. Observation: The Market Board**

Agents query `market_state.json` and `public_gallery/` to inspect:

- **Code Candidates ($C_{i}$):** Source code submitted by agents (readable by all)
- **Verifiers ($V_{j}$):** Executable functions that return true/false or timeout ($\perp$)
  - _Example:_ `def test_empty_input(func): assert func([]) == []`
  - _Value:_ Tests that discriminate between candidates (some pass, others fail)
- **Sentences ($\varphi$):** Tradeable claims:
  - _Verifier Validity ($\varphi_{V,j}$):_ "Verifier $V_{j}$ is a legitimate test of the problem statement"
  - _Candidate Quality ($\varphi_{G,i}$):_ "Candidate $k$ best satisfies the user's prompt"
- **Market Prices:** Current LMSR prices $P_t(\varphi)$ for all active sentences

#### **2. Inference: Private Sandbox**

Agents analyze code privately to generate trading alpha:

- **Self-Correction:** Patch own code to pass known tests (protecting their candidate's market price)
- **Attack Generation:** Write new verifiers targeting rival code bugs (to profit by shorting rivals)
- **Prediction:** Form beliefs about test outcomes and code quality based on analysis

#### **3. The Atomic Action: The Sealed Envelope**

All participants submit actions simultaneously (preventing information leakage):

**Action A (Propose New Asset): The Discovery Bond**

When an agent proposes a new sentence, they must stake a **forced long position** (bond) to back their discovery.

- **For Verifiers:** Bond staked on $\phi_{V,new}$ (validity of new test)
- **For Code Candidates:** Bond staked on $\phi_{G,new}$ (quality of new candidate)

**Mechanics:**

1. **New LMSR Market Created:**
   - Initial state: $q_{yes} = 0, q_{no} = 0$
   - Initial price: $P_0 = 0.5$ (neutral starting point for verifiers; $1/N$ for candidates)
   - Liquidity: $b_t$ calculated using current Whale wealth

2. **Proposer Buys Bond:**
   - Proposer stakes a target wager $W_{bond}$ on the LMSR at current price ($P_0 = 0.5$) to acquire $\Delta q_{bond}$ shares
   - Payment goes into LMSR cost function
   - Shares are locked for $N_{lock}$ ticks (cannot be sold immediately)

3. **Whale as Passive Counterparty:**
   - The Whale (as LMSR market maker) is automatically the counterparty
   - Whale holds the implicit short position via the LMSR cost function
   - Whale does NOT submit any active belief or trade for newly proposed verifier validity

4. **Price Movement:**
   - After bond purchase: $q_{yes} = \Delta q_{bond}$
   - New price: $P_1 > P_0$ (bond moved the market)
   - Other agents now see this price and can trade

**Entry Advantage:** The proposer gets to buy at the initial neutral price ($P_0 = 0.5$) before the market reacts. If the market eventually agrees the sentence is valuable (price rises to $P > 0.5$), the proposer captures the full price appreciation. If the market rejects it (price falls to $P < 0.5$), the proposer loses.

**Bond Maturation:** After $N_{lock}$ ticks, shares automatically sell back to LMSR at current price. Profit/loss = (exit price - entry price) × shares held.

**Action B (Update Candidate):** Submit a patch ($C_{k,v+1}$) to fix discovered bugs

**Action C (Bet):** Submit **Belief Vector** ($b_i$) for existing tradeable sentences
- **Inductive Agents:** Report beliefs $b_i(\phi) \in [0,1]$ based on LLM analysis
- **Whale:** Reports structural beliefs:
  - For verifier validity: Does NOT submit beliefs (remains passive at implicit b=0.5)
  - For candidate quality: $b_{whale}(\phi_{G,k})$ derived from softmax over test failures

### Phase C: Settlement

#### **1. Execution: The Oracle Run**

The Orchestrator executes all verifiers (old and newly proposed) in isolated `/tmp/` worktrees:

- **Binary Results:** Pass (exit 0), Fail (exit 1+), or Undefined ($\perp$ for timeout/error)
- **No Direct Payout:** Test results inform Whale beliefs but don't directly settle bets

#### **2. The Whale's Dual Behavior**

The Whale operates in two distinct modes:

**Mode 1: Passive LMSR Market Maker (All Sentences)**

For ALL sentences (both verifier validity and candidate quality):
- **Function:** The Whale IS the LMSR cost function
- **Mechanism:** When agents buy/sell shares, they transact with the Whale automatically
- **No Active Trading:** Whale never submits belief vectors for verifier validity
- **Result:** Always provides liquidity at current LMSR prices

**Mode 2: Active Deductive Trader (Candidate Quality Only)**

After tests execute, the Whale computes and TRADES beliefs on candidate quality:

- **Observes:** Which tests failed on which candidates
- **Computes Log-Survival Score:** For each candidate $i$:
  $$S_{i}=\sum_{j \in F_{i}} \ln(1-P(\varphi_{V,j}))$$
  where $F_i$ is the set of tests candidate $i$ failed

- **Softmax Normalization:** Derives belief vector:
  $$b_{whale}(\phi_{G,i})=\frac{e^{S_{i}}}{\sum_{k=1}^{N} e^{S_{k}}}$$

- **Submits These Beliefs:** These get converted to LMSR trades (like any other agent)

**Logical Effect:**
- If candidate fails high-validity test ($P \approx 1$): $S_i \to -\infty$, belief crashes
- If candidate fails low-validity test ($P \approx 0$): $S_i \approx 0$, minimal impact
- If candidate fails no tests: $S_i = 0$, neutral belief

**Fixed Budget:**
- Whale's wealth $W_{whale}$ remains constant except for:
  - LMSR losses (when providing liquidity)
  - Active trading costs (on candidate quality)
- No rebalancing occurs
- Whale can theoretically go bankrupt (termination condition)

**Wealth Conservation:**

Total system wealth strictly decreases over time:
$$W_{total,t} = \sum_{i=1}^m W_{i,t} + W_{whale,t} = 2B - \sum_{s=0}^{t-1}(\text{taxes collected at round } s)$$

This guarantees convergence: as wealth drains from the system, eventually termination conditions are met.

#### **3. Belief-to-Bet Conversion via Heuristic Kelly**

Since LLMs provide beliefs (not trading strategies), the Orchestrator converts beliefs to LMSR trades:

**Step A: Clip Beliefs (Safety)**
Prevent extreme confidence to avoid catastrophic losses:
$$b_{clipped}=\min(\max(b_{raw},\epsilon),1-\epsilon)$$
where $\epsilon = 0.01$ (agents can't be >99% confident)

**Step B: Compute Ideal Kelly Fractions**
For each sentence $j$, calculate the fraction of wealth to wager:
- If $b_{clipped} > P_t$: $f_j^* = \frac{b_{clipped} - P_t}{1 - P_t}$ (Long)
- If $b_{clipped} < P_t$: $f_j^* = \frac{b_{clipped} - P_t}{P_t}$ (Short)

*Interpretation:*
- $f^* > 0$ indicates a long position; $f^* < 0$ indicates a short position.
- Magnitude reflects the "edge" size relative to current risk.

**Step C: Portfolio Normalization (No Leverage)**
Ensure total intended wager doesn't exceed wealth:
$$L_{i}=\sum_{j} |f_{j}^{*}| + \sum_{k \in \text{NewProposals}} |f_{bond,k}|$$
$$\kappa_{i}=\frac{1}{\max(1,L_{i})}$$

If $L_i > 1$, scale down all positions (bets and bonds) proportionally.

**Step D: Convert to Target Wagers**
Instead of calculating individual LMSR share quantities (which causes overshooting if agents trade simultaneously), the orchestrator calculates the exact **Wager ($W_{i,j}$)** the agent wants to spend:
$$W_{i,j} = W_i \cdot \kappa_i \cdot f_j^*$$

Positive wagers indicate buying YES shares; negative wagers indicate buying NO shares (shorting).

#### **4. LMSR Price Update via Simultaneous Batching**

To ensure fairness and prevent "first-mover advantage," all trades within a round are executed simultaneously using a **Batch Wager Clearing** algorithm that perfectly respects the LMSR cost function's path independence.

**The Clearing Algorithm:**
For each sentence $\phi$ with current price $P_t$:
1. **Pool Wagers:** Sum all intended YES wagers ($W_{yes}$) and absolute NO wagers ($W_{no}$) across all agents and the Whale.
2. **Direct Matching:** Opposing wagers cancel each other out at the current marginal price $P_t$. The market matches the maximum possible wagers without moving the price:
   - $Q_{match} = \min(W_{yes} / P_t, W_{no} / (1 - P_t))$
   - This consumes $Q_{match} \cdot P_t$ of the YES budget and $Q_{match} \cdot (1-P_t)$ of the NO budget.
3. **Curve Pushing:** One side will have leftover wagers ($W_{rem}$). This remaining capital is used to push the LMSR cost curve:
   - $\Delta Q_{LMSR}$ is calculated using the exact inverse of the LMSR cost function for $W_{rem}$.
   - The market maker (Whale) absorbs this leftover wager, and the LMSR state ($q_{yes}$ or $q_{no}$) updates by $\Delta Q_{LMSR}$.
4. **Proportional Distribution:** The total shares created ($Q_{match} + \Delta Q_{LMSR}$) are distributed back to the agents proportionally based on their original $W_i$ contributions.

**Properties:**
- ✅ **First-Mover Fairness:** All agents trade against the exact same market conditions.
- ✅ **No Overshooting:** Agents never spend more than their calculated Kelly wager.
- ✅ **Automatically Zero-Sum:** The Whale perfectly balances the net LMSR movement.
- ✅ **Always Liquid:** Can always trade at current price
- ✅ **Bounded Loss:** Whale's max loss per round = $0.5 \cdot W_{whale,t}$ (by construction of $b_t$)
- ✅ **Incentive Compatible:** Truth-revealing (proper scoring rule)

**Execution Order:**
1. Recalculate $b_t$ based on current Whale wealth and active markets
2. Snapshot the current Market State (prices and verifier confidences).
3. Agents and Whale calculate target Wagers based on the frozen snapshot.
4. Execute all wagers simultaneously via the Batch Clearing Algorithm.
5. Prices update to new equilibrium via LMSR formula.

#### **5. Instant Settlement (Mark-to-Market)**

At the end of each round, all belief-based positions (non-bond shares) are settled into liquid wealth. This ensures agents can re-allocate their entire capital every round based on new information.

**Mechanism:**
1. **Valuation:** The Orchestrator calculates the "Credit Value" of each agent's current position using the final LMSR price of the round.
2. **Wealth Transfer:** The Whale (Market Maker) pays the agent the market value of their shares in compute credits.
3. **Whale Absorption:** Instead of being sold back to the pool (which would crash the price), the shares are transferred to the Whale's private inventory.

**Why this is used:**
- ✅ **Preserves Price Discovery:** By absorbing the shares, the Whale maintains the current market consensus into the next round.
- ✅ **Prevents Capital Lockup:** Agents aren't "stuck" in old positions and can bet their full wealth on new realizations every tick.
- ✅ **Ensures Solvency:** Forces a clean reconciliation of wealth for accurate bankruptcy checks.

#### **6. Wealth Updates**

**For Agents:**
$$W_{i,t+1} = W_{i,t} - \sum_{j} \text{Cost}_{i,j} - T_{inf}$$

Where:
- $\text{Cost}_{i,j}$: Net cost of LMSR trades on sentence $j$ (can be negative = profit)
- $T_{inf}$: Inference tax (fixed per round)
- $N_{proposals}$: Number of new assets proposed this round (no explicit fee; bond requirement prevents spam)

**For Whale:**
$$W_{whale,t+1} = W_{whale,t} - \sum_{j} \text{Cost}_{whale,j}$$

Where:
- $\text{Cost}_{whale,j}$: Net cost from LMSR trades and liquidity provision
- No rebalancing occurs
- Whale wealth only changes via trading and market making

**Wealth Conservation:**
$$\sum_i W_{i,t+1} + W_{whale,t+1} = 2B - \sum_{s=0}^{t}(\text{total taxes collected at round } s)$$

Total wealth strictly decreases by the amount of taxes collected each round.

**Bond Maturation:**
When bond unlocks (after $N_{lock}$ ticks):
- Shares automatically sold back to LMSR at current price
- Profit/loss = (exit price - entry price) × shares held
- If price rose: agent profits (captured information alpha)
- If price fell: agent loses (market rejected proposal)

#### **7. Agent Cleanup**

**Bankruptcy:** If $W_{i, total} \leq T_{inf}$ where $W_{i, total}$ is the agent's total net worth including both liquid wealth ($W_i$) and the current market value of all their locked bonds:
- Agent is eliminated from market
- Any locked bonds are liquidated at current prices
- Wealth transfers to Whale (who took opposite side of their trades)

### Phase D: Market Settlement & Convergence

The market doesn't run indefinitely—it converges naturally through economic pressures and hits a **termination condition**.

#### **Convergence Mechanisms**

1. **Economic Attrition (Inference Tax):**
   - Agents pay $T_{inf}$ every round
   - Poor predictors lose wealth faster than they gain it
   - Eventually only accurate traders survive
   - Total agent wealth: $\sum_i W_i \to 0$ as $t \to \infty$

2. **Information Saturation:**
   - As code improves, finding new bugs becomes exponentially harder
   - Cost of discovering bug (inference cost) exceeds potential profit (from price movement)
   - Agents stop proposing new verifiers (not profitable)
   - Price volatility decreases

3. **Wealth Concentration:**
   - Best predictors accumulate wealth
   - Their beliefs dominate market prices
   - Minority trader beliefs have negligible impact
   - Effective consensus achieved

#### **Termination Conditions**

The Orchestrator halts when **any** of the following occurs:

**Condition 1: Price Stability**

The market has converged when the volatility of candidate quality prices over the last 10 rounds falls below a threshold. Volatility is measured as the standard deviation of prices across all candidates over the recent window. Threshold: $\epsilon_v = 0.01$.

**Condition 2: Wealth Concentration (Gini Coefficient)**

The market terminates if wealth becomes too concentrated, indicating a single agent has dominated. The Gini coefficient measures inequality in the wealth distribution. Threshold: $\epsilon_g = 0.8$ (one agent controls approximately 80% or more of total wealth).

**Condition 3: Agent Bankruptcy**

If the total wealth held by all agents falls below a critical threshold, the market terminates. This indicates the inference tax has drained most capital from the system. Threshold: $\epsilon_w \cdot B = 0.1B$ (less than 10% of initial capital remains with agents).

**Condition 4: Whale Bankruptcy**

If the Whale's wealth falls below a safety threshold, the market terminates with a failure signal. This indicates agents collectively exploited the market maker or there's an implementation bug. Threshold: $0.05B$ (Whale has less than 5% of its initial capital).

**Condition 5: Hard Round Limit**

As a safety valve, the market terminates after a maximum number of rounds regardless of other conditions. Typical limit: $t_{max} = 100$ rounds.

#### **Winner Selection**

Upon termination, the **winning candidate** is determined by:

**Primary Method:** Highest master goal price
$$\text{Winner} = \arg\max_k P_{final}(\phi_{G,k})$$

**Tiebreaker (if prices within ε):** Lowest failure count
$$\text{Winner} = \arg\min_k |F_k|$$

where $F_k$ is the set of valid tests (P > 0.5) that candidate $k$ failed.

**Human Review:** The orchestrator presents:
- Winning candidate code
- Final test suite (all verifiers with P > 0.5)
- Market history visualization (price trajectories)
- Agent wealth evolution

User can accept, reject, or request additional rounds.

## 3. Incentive Dynamics (Why It Works)

This formal structure creates specific evolutionary pressures:

### **1. The "Sure-Thing" Sink**
- **Scenario:** Agent A proposes `assert True` (passes for everyone)
- **Market Reaction:**
  - Other agents recognize test provides no information
  - They short the validity: $b_i(\phi_V) \approx 0.1$
  - Whale remains passive (doesn't trade on verifier validity)
- **Price Movement:** $P(\phi_V) \to 0.2$ (low validity consensus)
- **Outcome:**
  - Proposer's bond loses value (bought at 0.5, sells at 0.2)
  - Net loss for wasting market's time (bond acts as implicit proposal fee)

### **2. The "Discriminating Test" Jackpot**
- **Scenario:** Agent B proposes test that fails candidate 1 but passes candidates 2,3
- **Market Reaction:**
  - Test provides valuable information (splits candidates)
  - Agents long the validity: $b_i(\phi_V) \approx 0.9$
  - Whale remains passive
- **Price Movement:** $P(\phi_V) \to 0.8$ (high validity consensus)
- **Outcome:**
  - Proposer's bond gains value (bought at 0.5, sells at 0.8)
  - Reward for discovering useful test

### **3. The "Adversarial Alpha" Play**
- **Scenario:** Market optimistic on candidate C ($P(\phi_{G,C}) = 0.9$). Agent D finds subtle bug.
- **Agent D's Strategy:**
  1. Propose test exposing bug (bond on test validity)
  2. Short candidate C (bet $b_D(\phi_{G,C}) = 0.1$)
  3. Patch own candidate to pass new test
- **After Oracle Execution:**
  - Test runs: C fails, D's candidate passes
  - Whale observes failure, computes: $b_{whale}(\phi_{G,C}) \to 0.2$ (softmax penalty)
  - Whale TRADES this belief (actively shorts C)
  - Price crashes: $P(\phi_{G,C}): 0.9 \to 0.3$
- **Outcome:**
  - Agent D profits from short position (sold high at 0.9, bought back at 0.3)
  - Bond on test validity likely succeeds (test was informative)
  - Agent D's own candidate benefits (relative improvement)
  - **Incentivizes deep adversarial testing**

### **4. The "Fix Your Bug" Pressure**
- **Scenario:** Agent E's candidate fails a high-validity test ($P(\phi_V) = 0.9$)
- **Whale Response:** Penalizes via softmax: $\Delta S_E = \ln(1-0.9) \approx -2.3$
- **Price Impact:** $P(\phi_{G,E})$ drops significantly due to Whale's active trading
- **Agent E's Options:**
  1. **Fix the bug:** Patch code to pass test (prevents further price drop)
  2. **Dispute validity:** Short the test's validity (risky—must convince market test is wrong)
- **Equilibrium:** Agents fix real bugs (cheaper than losing market share)

### **5. Portfolio Diversification Effects**
- **Partisan Voting Problem:** Why don't agents just vote their own tests "valid"?
- **Answer:** Agents own multiple candidates or have diversified positions
- **Example:**
  - Agent owns candidates A, C
  - Test T fails A but passes B, C, D
  - Agent should vote "valid" because:
    - Helps C relative to B, D (net positive for portfolio)
    - Lying (voting "invalid") damages own credibility
    - Other agents will detect and exploit dishonesty
- **Result:** Truth-telling is portfolio-optimal

## 4. Formal System Specification

This section provides a complete, self-contained mathematical specification of the market. All terms and parameters are defined here.

### System Definition

The market is a discrete-time dynamical system $\Sigma = \langle \mathcal{A}, \Phi, \mathcal{M}, \mathcal{O}, \mathcal{W} \rangle$ operating over rounds $t = 0, 1, 2, \ldots$

**Components:**

- **$\mathcal{A} = \{a_1, \ldots, a_m, a_{whale}\}$**: The set of market participants
  - $a_1, \ldots, a_m$: The Sharks (inductive agents)
  - $a_{whale}$: The Whale (deductive agent + market maker)
  - $m$: Number of Shark agents (typically $m = N$ where $N$ is from initialization)

- **$\Phi_t = \Phi_V \cup \Phi_G$**: The set of active sentences at round $t$
  - $\Phi_V = \{\varphi_{V,1}, \varphi_{V,2}, \ldots\}$: Verifier validity sentences
  - $\Phi_G = \{\varphi_{G,1}, \varphi_{G,2}, \ldots, \varphi_{G,N}\}$: Candidate quality sentences
  - Each $\varphi$ is a logical claim that can be true or false

- **$\mathcal{M}_t = \{M_\varphi : \varphi \in \Phi_t\}$**: The set of LMSR markets
  - One market $M_\varphi$ per sentence $\varphi$
  - Each market tracks shares outstanding and provides pricing

- **$\mathcal{O}: \Phi \to \{0, 1, \perp\}$**: The Oracle function
  - Maps sentences to truth values
  - $\mathcal{O}(\varphi) = 1$: Test passes
  - $\mathcal{O}(\varphi) = 0$: Test fails
  - $\mathcal{O}(\varphi) = \perp$: Undefined (timeout, unverifiable, or not yet executed)

- **$\mathcal{W}_t = (W_{1,t}, \ldots, W_{m,t}, W_{whale,t}) \in \mathbb{R}_{\geq 0}^{m+1}$**: The wealth vector
  - $W_{i,t}$: Wealth of agent $a_i$ at round $t$ (in compute credits)
  - Initial condition: $W_{i,0} = B/N$ for all Sharks
  - Initial condition: $W_{whale,0} = B$
  - Conservation: $\sum_{i=1}^m W_{i,t} + W_{whale,t} = 2B - \sum_{s=0}^{t-1}(\text{taxes}_s)$ (strictly decreasing)

**Parameters (Constants):**

- $B$: Total budget (in compute credits)
- $N$: Number of initial candidates (typically $N = m$)
- $b_{min}$: Minimum LMSR liquidity parameter ($b_{min} = B/200$ typically)
- $T_{inf}$: Inference tax per round (e.g., $T_{inf} = 0.01 \cdot B/N$)
- $\epsilon$: Belief clipping parameter ($\epsilon = 0.01$)
- $N_{lock}$: Bond lock period in rounds (e.g., $N_{lock} = 1$)

### A. Sentences & Assets

Every tradeable asset is a sentence $\varphi$ with an associated LMSR market $M_\varphi$.

**Verifiable Sentences ($\varphi_{V,j} \in \Phi_V$):**
- **Definition:** Claims about the validity of a verifier (test function)
- **Text form:** "Verifier $V_j$ is a legitimate test of the problem statement"
- **Verifier:** Possess computable function $V_\varphi: \text{Code} \to \{0, 1, \perp\}$
- **Oracle:** $\mathcal{O}(\varphi_{V,j})$ determined by executing $V_j$ on candidates
  - If $V_j$ passes on some candidates and fails on others → splits candidates → likely valid
  - If $V_j$ passes or fails on all candidates → doesn't discriminate → likely invalid
- **Implementation:** Python function that returns boolean or times out

**Unverifiable Sentences ($\varphi_{G,k} \in \Phi_G$):**
- **Definition:** Claims about code candidate quality
- **Text form:** "Candidate $k$ best satisfies the user's prompt"
- **Verifier:** No direct verifier function
- **Oracle:** $\mathcal{O}(\varphi_{G,k}) = \perp$ always (inherently unverifiable)
- **Market Logic:** Price determined by:
  - Correlation with verifiable sentences (if tests fail, quality drops)
  - Agent beliefs (LLM assessments of code quality)
  - Whale's deductive enforcement (softmax over test failures)

### B. LMSR Markets

Each sentence $\varphi \in \Phi_t$ has an associated LMSR market $M_\varphi$ with the following state:

**State Variables:**
- $q_{yes,\varphi,t}$: Total YES shares outstanding at round $t$
- $q_{no,\varphi,t}$: Total NO shares outstanding at round $t$
- $b_t$: Liquidity parameter (recalculated each round)

**Dynamic Liquidity Parameter:**

At the start of each round $t$, recalculate:
$$b_t = \max\left(b_{min}, \frac{0.5 \cdot W_{whale,t}}{M_{active,t} \cdot \ln(2)}\right)$$

where:
- $M_{active,t} = |\Phi_t|$: Number of active markets
- $b_{min} = B/200$: Minimum liquidity floor
- Purpose: Ensures Whale cannot lose more than 50% wealth in one round

**Price Function:**
$$P_t(\varphi) = \frac{\exp(q_{yes,\varphi,t}/b_t)}{\exp(q_{yes,\varphi,t}/b_t) + \exp(q_{no,\varphi,t}/b_t)}$$

*Interpretation:* $P_t(\varphi)$ is the market's current probability that sentence $\varphi$ is true.

**Cost Function:**
$$C_\varphi(q_{yes}, q_{no}) = b_t \cdot \ln\left(\exp(q_{yes}/b_t) + \exp(q_{no}/b_t)\right)$$

*Purpose:* Determines how much an agent must pay to change share quantities.

**Executing a Target Wager:**
When an agent $a_i$ wagers amount $W > 0$ on YES shares:
They acquire $\Delta q_{yes}$ shares such that:
$$C_\varphi(q_{yes,\varphi,t} + \Delta q_{yes}, q_{no,\varphi,t}) - C_\varphi(q_{yes,\varphi,t}, q_{no,\varphi,t}) = W$$

When agent $a_i$ wagers amount $W > 0$ on NO shares (Shorting):
They acquire $\Delta q_{no}$ shares such that:
$$C_\varphi(q_{yes,\varphi,t}, q_{no,\varphi,t} + \Delta q_{no}) - C_\varphi(q_{yes,\varphi,t}, q_{no,\varphi,t}) = W$$

*Note: In the Simultaneous Batch Clearing mechanism, all opposing wagers are first matched at the current price before applying the net remaining wager to push the cost function.*

**Market Update:**
Update the corresponding $q_{yes}$ or $q_{no}$ based on the trade.

**Key Properties:**
- **Proper Scoring:** Agents maximize expected wealth by reporting true beliefs.
- **Zero-Sum:** All payments are transacted with the Whale via the cost function.
- **Always Liquid:** Can always trade at current $P_t(\varphi)$.
- **Bounded Loss per Round:** Whale's max loss ≤ $0.5 \cdot W_{whale,t}$ (by construction of $b_t$).

### C. Agent Beliefs & Actions

**Belief Vectors:**
Each agent $a_i$ at round $t$ holds beliefs:
$$b_{i,t}: \Phi_t \to [0,1]$$

where $b_{i,t}(\varphi)$ is agent $i$'s subjective probability that sentence $\varphi$ is true.

**Whale Belief Structure:**
The Whale has special beliefs:

- **For Verifier Validity ($\varphi \in \Phi_V$):** No explicit belief (passive market maker)
- **For Candidate Quality ($\varphi_{G,k} \in \Phi_G$):**
  
  **Step 1 - Log-Survival Score:**
  $$S_{k,t} = \sum_{j: \mathcal{O}(V_j, C_k) = 0} \ln(1 - P_t(\varphi_{V,j}))$$
  
  *where*:
  - $\mathcal{O}(V_j, C_k) = 0$ means verifier $V_j$ failed on candidate $C_k$
  - $P_t(\varphi_{V,j})$ is the market's current belief in test $j$'s validity
  
  *Interpretation*: Each test failure penalizes the survival score by the log-uncertainty of that test's validity.
  
  **Step 2 - Softmax Normalization:**
  $$b_{whale,t}(\varphi_{G,k}) = \frac{\exp(S_{k,t})}{\sum_{k'=1}^N \exp(S_{k',t})}$$
  
  *Property*: $\sum_{k=1}^N b_{whale,t}(\varphi_{G,k}) = 1$ (beliefs sum to 1 across candidates)

**Action Types:**

Each round, agent $a_i$ can perform:

1. **Propose New Asset:** Submit new verifier $V_{new}$ or candidate $C_{new}$
   - Creates new sentence $\varphi_{new}$
   - Requires bond: stake a wager $W_{bond}$ at $P_0 = 0.5$ (prevents spam). Bond size is determined by a Kelly bet with maximal belief $b = 1-\epsilon$.
   - Shares locked for $N_{lock}$ rounds

2. **Update Code:** Submit patch $C_{k} \to C_{k}'$ (no direct cost, but requires inference)

3. **Submit Beliefs:** Report belief vector $b_{i,t}$ for all sentences
   - Converted to LMSR trades via Kelly heuristic (see subsection D)

### D. Belief-to-Trade Conversion (Kelly Heuristic)

The Orchestrator converts belief vectors to LMSR trades using the following algorithm:

**Input:**
- Agent $a_i$ with wealth $W_{i,t}$
- Belief vector $b_{i,t}$
- Current prices $P_t$

**Step 1 - Clip Beliefs:**
$$b_{i,t}^{clip}(\varphi) = \max(\epsilon, \min(1-\epsilon, b_{i,t}(\varphi)))$$

where $\epsilon = 0.01$ (prevents extreme confidence)

**Step 2 - Compute Ideal Kelly Fractions:**
For each sentence $\varphi$:
- If $b_{i,t}^{clip} > P_t$: $f_{\varphi}^* = \frac{b_{i,t}^{clip} - P_t}{1 - P_t}$ (Long)
- If $b_{i,t}^{clip} < P_t$: $f_{\varphi}^* = \frac{b_{i,t}^{clip} - P_t}{P_t}$ (Short)

*Interpretation:*
- $f_{\varphi}^* > 0$: Want to long (buy YES shares)
- $f_{\varphi}^* < 0$: Want to short (buy NO shares)
- $|f_{\varphi}^*|$: Fraction of wealth to wager

**Step 3 - Normalize Portfolio (No Leverage):**
$$L_i = \sum_{\varphi \in \Phi_t} |f_{\varphi}^*| + \sum_{k \in \text{NewProposals}} |f_{bond,k}|$$

$$\kappa_i = \frac{1}{\max(1, L_i)}$$

*Purpose:* If total desired exposure (bets + bonds) exceeds 100% of wealth, scale down all positions proportionally.

**Step 4 - Calculate Target Wagers:**
For each sentence $\varphi$ (existing or newly proposed), calculate the target wager $W_{i,\varphi} = W_{i, t} \cdot \kappa_i \cdot f_{\varphi}^*$.

**Output:** Set of target wagers $\{(\varphi, W_{i,\varphi})\}_{\varphi \in \Phi_t}$

### E. Wealth Dynamics

**Within-Round Wealth Updates:**

After all agents submit their wagers in round $t$:

1. **Recalculate Liquidity:** Update $b_t$ based on current $W_{whale,t}$ and $M_{active,t}$

2. **Simultaneous Batch Clearing:** For each sentence $\varphi$, pool all YES wagers and NO wagers across all participants. Match opposing wagers at current price $P_t$, then apply the remaining wager to push the LMSR curve.

3. **Trade Costs:** Agents are charged exactly their target wagers.
   $$\text{Cost}_{i,\varphi,t} = |W_{i,\varphi}|$$
   
4. **Aggregate Wealth Change from Trading:**
   $$\Delta W_{i,t}^{trade} = -\sum_{\varphi \in \Phi_t} \text{Cost}_{i,\varphi,t}$$
   
5. **Taxes:**
   $$\Delta W_{i,t}^{taxes} = -T_{inf}$$

**End-of-Round Wealth:**
$$W_{i,t+1} = W_{i,t} + \Delta W_{i,t}^{trade} + \Delta W_{i,t}^{taxes}$$

**Whale Wealth (No Rebalancing):**
$$W_{whale,t+1} = W_{whale,t} - \sum_{\varphi \in \Phi_t} \text{Cost}_{whale,\varphi,t}$$

where $\text{Cost}_{whale,\varphi,t}$ is the Whale's net cost from LMSR liquidity provision and active trading.

**Conservation Law:**
$$\sum_{i=1}^m W_{i,t+1} + W_{whale,t+1} = 2B - \sum_{s=0}^{t} (\text{total taxes at round } s)$$

Total wealth strictly decreases each round by the amount of inference tax collected.

**Bond Maturation:**

If bond from round $t_0$ unlocks at round $t_0 + N_{lock}$:
- Shares held: $\Delta q_{bond}$
- Entry price: $P_{t_0}(\varphi) = 0.5$
- Exit price: $P_{t_0+N_{lock}}(\varphi)$
- Shares sold back to LMSR automatically
- Net profit/loss already reflected in wealth (LMSR automatically settles)

### F. Termination Conditions

Define termination predicate $\mathcal{T}(t)$:

$$\mathcal{T}(t) = \bigvee_{i=1}^5 \mathcal{T}_i(t)$$

where:

**$\mathcal{T}_1(t)$ - Price Stability:**
$$\text{Volatility}_t = \text{std}\left(\{P_s(\varphi_{G,k})\}_{k=1}^N\right)_{s=t-9}^t$$
$$\mathcal{T}_1(t) = [\text{Volatility}_t < \epsilon_v]$$

where $\epsilon_v = 0.01$ and we compute standard deviation over last 10 rounds.

**$\mathcal{T}_2(t)$ - Wealth Concentration:**
$$\text{Gini}(W_t) = \frac{\sum_{i=1}^m \sum_{j=1}^m |W_{i,t} - W_{j,t}|}{2m \sum_{i=1}^m W_{i,t}}$$
$$\mathcal{T}_2(t) = [\text{Gini}(W_t) > \epsilon_g]$$

where $\epsilon_g = 0.8$ (one agent controls ~80%+ of wealth)

**$\mathcal{T}_3(t)$ - Agent Bankruptcy:**
$$\mathcal{T}_3(t) = \left[\sum_{i=1}^m W_{i,t} < \epsilon_w \cdot B\right]$$

where $\epsilon_w = 0.1$ (less than 10% of initial capital remains)

**$\mathcal{T}_4(t)$ - Whale Bankruptcy:**
$$\mathcal{T}_4(t) = [W_{whale,t} < 0.05 \cdot B]$$

*Note:* Indicates agents collectively exploited market maker or implementation bug.

**$\mathcal{T}_5(t)$ - Hard Limit:**
$$\mathcal{T}_5(t) = [t > t_{max}]$$

where $t_{max} = 100$ rounds typically.

**Termination Round:** $T = \min\{t : \mathcal{T}(t)\}$

### G. Winner Selection

At termination round $T$, the winning candidate is:

$$k^* = \arg\max_{k \in \{1,\ldots,N\}} P_T(\varphi_{G,k})$$

**Tiebreaker (if $|P_T(\varphi_{G,k_1}) - P_T(\varphi_{G,k_2})| < \epsilon_{tie}$ for some $k_1, k_2$):**

Define failure set:
$$F_k = \{j : \mathcal{O}(V_j, C_k) = 0 \text{ and } P_T(\varphi_{V,j}) > 0.5\}$$

Then:
$$k^* = \arg\min_{k} |F_k|$$

*Interpretation:* Choose candidate with fewest failures on high-confidence valid tests.

### H. Summary of System Dynamics

**One Complete Round ($t \to t+1$):**

1. **Observation:** Agents query market state $(P_t, W_t)$ and code $\{C_k\}$
2. **Oracle Execution:** Run all verifiers, get $\mathcal{O}(V_j, C_k)$ for all $(j,k)$
3. **Whale Belief Update:** Compute $b_{whale,t+1}$ via softmax (only for $\Phi_G$)
4. **Agent Belief Submission:** Agents submit $b_{i,t}$
5. **Liquidity Recalculation:** Update $b_t$ based on current Whale wealth
6. **Trade Conversion:** Convert beliefs to target Wagers via Kelly heuristic
7. **Trade Execution:** Execute all wagers simultaneously via Batch Clearing, deduct costs, and update LMSR markets
8. **Instant Settlement:** Resolve belief-based trades into liquid wealth; Whale absorbs shares to preserve price discovery
9. **Tax Application:** Deduct $T_{inf}$ from agent wealth
10. **Bankruptcy Check:** Remove agents with total net worth $\leq T_{inf}$
11. **Bond Maturation:** Unlock and settle bonds from round $t - N_{lock}$
12. **Termination Check:** If $\mathcal{T}(t+1)$, terminate and select winner

## 5. Implementation

### Overview & Design Philosophy

The tournament system is implemented as a **custom OpenCode tool** that orchestrates multiple headless agent sessions within a single process. The design shifts complexity from environment configuration (Docker containers, network isolation) to market logic (in-memory LMSR state) while maintaining clean separation between agents through filesystem permissions and isolated session databases.

The goal is to create a "disposable universe" for each tournament—a self-contained workspace in `/tmp/` that contains all agent code, test cases, and market state, which can be completely deleted after the tournament concludes. This approach keeps the main project clean while allowing agents to freely read rival code and propose adversarial tests.

### Tool Integration with OpenCode

The tournament is exposed to OpenCode's LLM as a **custom tool** using OpenCode's plugin system.

**Tool Definition:**

The tool is registered via an OpenCode plugin that defines the tournament interface:

```typescript
// In .opencode/plugins/tournament.ts
import { Plugin, tool } from '@opencode-ai/plugin'

export const TournamentPlugin: Plugin = async (ctx) => {
  return {
    tool: {
      run_tournament: tool({
        description: 'Run a Logical Induction Market tournament to solve a coding problem',
        args: {
          prompt: tool.schema.string().describe('The coding problem to solve'),
          n_agents: tool.schema.number().default(3).describe('Number of competing agents'),
          budget: tool.schema.number().default(1000).describe('Total compute budget'),
          max_rounds: tool.schema.number().default(100).describe('Maximum tournament rounds')
        },
        async execute(args, context) {
          // Spawn tournament orchestrator and dashboard
          // Return results when complete
        }
      })
    }
  }
}
```

**Invocation Flow:**

1. **User initiates via chat:** "Run a tournament to solve [problem]"
2. **LLM recognizes pattern:** Calls `run_tournament` tool with extracted parameters
3. **Tool spawns orchestrator:** Subprocess managing market rounds
4. **Dashboard renders:** TUI overlay showing live tournament status
5. **Blocking execution:** Main session waits for completion (but displays updates)
6. **Results returned:** Winner code, test suite, and market history

**TUI Integration:**

The tool creates a Bubble Tea dashboard component that renders as an overlay in the main OpenCode TUI. This dashboard:
- Updates reactively via Server-Sent Events from orchestrator
- Displays live price charts, standings, and events
- Accepts keyboard input (minimize, cancel, accept winner)
- Returns control to main session when tournament completes

### Filesystem & Permissions Structure

To keep the main project clean, the Orchestrator creates a **"Disposable Universe"** in `/tmp/`. This folder contains everything specific to this run: agent code, private memories, and test cases (verifiers) that agents generate to attack each other.

**Permission Model:**

The system uses OS-level permissions to enforce isolation while allowing read access:
- **Write Access:** Each agent can only write to its own worktree and session database
- **Read/Execute Access:** All agents can read all code and execute all verifiers
- **Oracle Execution:** When an agent proposes a verifier, the orchestrator executes it against all candidate worktrees

**Filesystem Layout:**

```
# 1. THE PERMANENT UNIVERSE (Your Project Root)
/Users/amal/projects/my-app/           (Owner: amal, Perms: 755 [rwxr-xr-x])
│
├── src/                               # Protected source code
├── .opencode/plugins/tournament.ts    # Tournament tool plugin
└── .git/                              # READ-ONLY for all agents

---------------------------------------------------------------------------

# 2. THE DISPOSABLE UNIVERSE (Created in /tmp/ during run)
/tmp/opencode_market_28a9/             (Owner: amal, Perms: 755 [rwxr-xr-x])
│
├── market_state.json                  (Owner: amal, Perms: 600 [rw-------])
│
├── worktrees/                         (Owner: amal, Perms: 755 [rwxr-xr-x])
│   ├── candidate_0/
│   │   └── solution.py                <-- Agent 0 can WRITE; others can READ
│   ├── candidate_1/
│   │   └── solution.py                <-- Agent 1 can WRITE; others can READ
│   └── ...
│
├── sessions/                          (Owner: amal, Perms: 711 [rwx--x--x])
│   ├── agent_0.db                     (Owner: amal, Perms: 600 [rw-------])
│   ├── agent_1.db                     (Owner: amal, Perms: 600 [rw-------])
│   └── ...
│
└── verifiers/                         (Owner: amal, Perms: 755 [rwxr-xr-x])
    ├── v_8f2a1b/                      # SCOPED TEST PACKAGES
    │   ├── run.sh                    <-- ALL agents can READ/EXECUTE
    │   └── metadata.json
    └── v_c3d9e4/
```

**Design Rationale:**

This "open border" permission model serves several purposes:
1. **Transparency:** Agents can analyze rival solutions (encouraging adversarial testing)
2. **Constructive Competition:** Must propose tests that discriminate (you pass, opponent fails)
3. **Simplicity:** No complex sandboxing; rely on filesystem permissions
4. **Auditability:** All code and tests visible in plain filesystem for debugging

### Core Architecture Components

The system consists of four primary components communicating via async message passing:

#### 1. **Orchestrator (Main Process)**

The orchestrator manages the tournament lifecycle and acts as the central coordinator.

**Responsibilities:**
- Spawn N agent sessions (headless OpenCode instances)
- Execute discrete market rounds (the "tick")
- Run oracle (execute verifiers in isolated subprocesses)
- Convert agent beliefs to LMSR trades
- Apply economic rules (inference tax, bankruptcy)
- Emit progress updates to dashboard
- Serialize state periodically (crash recovery)

**Execution Model:**
Single Python process using `asyncio`. Agent inference happens concurrently via `asyncio.gather()`, but market settlement is sequential and atomic to ensure deterministic state transitions.

#### 2. **Agent Sessions (Headless OpenCode Instances)**

Agents are standard `OpenCodeSession` objects running in headless mode.

**Isolation Mechanism:**
Each agent gets a unique storage path (`/tmp/sessions/agent_N.db`) to prevent context leakage. Sessions reuse OpenCode's existing token window management, history truncation, and context handling—no custom LLM implementation needed.

**Market Injection:**
At each round, the orchestrator programmatically injects the current market state into the agent's system prompt, transforming it from a "coding assistant" into a "strategic trader."

**Belief Extraction:**
Agents return structured responses (JSON) containing:
- Belief vector (sentence_id → probability, **sparse** representation)
- Optional code updates
- Optional verifier proposals

#### 3. **The Whale (In-Process Pure Logic)**

The Whale runs as pure Python functions within the orchestrator—no separate process, no LLM calls.

**Dual Behavior:**
- **Passive LMSR Market Maker:** Provides liquidity automatically via cost function (structural role)
- **Active Deductive Trader:** Computes and submits beliefs on candidate quality based on softmax over test failures

#### 4. **Dashboard (TUI Overlay)**

A Bubble Tea component rendering in the main OpenCode session.

**Display Elements:**
- Live ASCII price chart (updates each round)
- Current standings (sorted by market price)
- Recent events (proposals, bankruptcies, convergence signals)
- Status indicators (round counter, active agents, termination progress)

**Interactivity:**
- Keyboard shortcuts for minimize, detail view, cancel
- Non-blocking updates via reactive rendering
- Returns winner to main session on completion

### Interface Definitions

The system is structured around three primary interfaces to maintain modularity and allow future execution model changes (e.g., Docker containers, distributed agents).

#### A. Market State Interface

Manages the authoritative state of markets, wealth, and sentences.

```python
class MarketState:
    """
    Central ledger tracking all market state
    
    Responsibilities:
    - Maintain LMSR market state (shares outstanding, prices)
    - Track agent and Whale wealth
    - Manage sentence registry (metadata, verifier paths)
    - Handle bond lifecycle (creation, maturation)
    - Calculate dynamic liquidity parameter
    """
    
    def calculate_liquidity(self) -> float:
        """
        Compute b_t based on current Whale wealth and active markets
        Returns liquidity parameter ensuring 50% max loss per round
        """
        ...
    
    def serialize(self) -> dict:
        """
        Export complete state to JSON for persistence/recovery
        """
        ...
    
    def get_prices(self) -> dict[str, float]:
        """
        Return current LMSR prices for all active sentences
        """
        ...
```

#### B. Oracle Interface

Manages verifier execution in isolation with timeout handling.

```python
class OracleExecutor:
    """
    Executes verifiers against candidate code in isolated subprocesses
    
    Responsibilities:
    - Run verifier against target worktree
    - Enforce timeout (default 5s)
    - Handle non-terminating/crashing verifiers
    - Return Pass/Fail/Undefined (⊥)
    """
    
    async def execute_verifier(
        self,
        verifier_path: str,
        candidate_worktree: str,
        timeout: float = 5.0
    ) -> VerifierResult:
        """
        Run verifier in subprocess with resource limits
        
        Returns:
            PASS: Exit code 0
            FAIL: Exit code != 0
            UNDEFINED: Timeout or crash
        """
        ...
    
    async def execute_all(
        self,
        verifiers: list[str],
        candidates: list[str]
    ) -> dict[tuple[str, str], VerifierResult]:
        """
        Run all verifiers against all candidates in parallel
        Returns grid of results: (verifier_id, candidate_id) -> result
        """
        ...
```

#### C. Agent Interface

Bridges OpenCode sessions with the tournament market.

```python
class TournamentAgent:
    """
    Wrapper around OpenCodeSession for market participation
    
    Responsibilities:
    - Maintain isolated session (unique storage path)
    - Inject market state into agent prompt each round
    - Extract structured responses (beliefs, actions)
    - Handle timeouts and malformed responses
    """
    
    async def get_move(self, snapshot: MarketSnapshot) -> AgentMove:
        """
        Present market state, request agent's next action
        
        Args:
            snapshot: Read-only market view (prices, code, events)
            
        Returns:
            AgentMove containing:
            - beliefs: Sparse dict[sentence_id, float] (no default)
            - code_update: Optional patch to own candidate
            - verifier_proposal: Optional new test with bond size
        """
        ...
```

#### D. Trading Engine Interface

Converts beliefs to LMSR trades using Kelly heuristic.

```python
class TradingEngine:
    """
    Translates agent beliefs into LMSR share purchases
    
    Responsibilities:
    - Clip beliefs to prevent extreme confidence
    - Compute Kelly fractions for portfolio
    - Normalize to prevent leverage (total exposure ≤ 100%)
    - Generate LMSR trade instructions
    """
    
    def beliefs_to_trades(
        self,
        agent_id: str,
        beliefs: dict[str, float],  # Sparse! Only reported beliefs
        wealth: float,
        current_prices: dict[str, float],
        liquidity: float
    ) -> list[Trade]:
        """
        Apply Kelly heuristic to convert beliefs to trades
        
        Missing beliefs are NOT defaulted to 0.5
        No belief = no trade (avoids unintended large positions)
        
        Returns list of trades: (sentence_id, delta_q, cost)
        """
        ...
```

### Round Execution Flow

Each round follows a deterministic sequence:

1. **Observation:** Agents query market state concurrently
2. **Oracle Execution:** Run all verifiers against all candidates (parallel)
3. **Whale Belief Update:** Compute softmax beliefs based on test results
4. **Liquidity Recalculation:** Update $b_t$ based on current Whale wealth
5. **Agent Submission:** Collect belief vectors and actions (with timeout)
6. **Trade Conversion:** Convert all beliefs (Whale + agents) to LMSR trades
7. **Atomic Settlement:** Execute all trades sequentially, update markets
8. **Economic Rules:** Apply inference tax, process bankruptcies
9. **Bond Management:** Unlock matured bonds, create new ones
10. **Dashboard Update:** Emit events to TUI for display
11. **Termination Check:** Evaluate convergence conditions

This flow ensures deterministic state evolution and makes the system fully reproducible from serialized state.

### Error Handling & Edge Cases

**Agent Timeout:**
- If agent doesn't respond within 60s, forfeit round (no trades, no actions)
- Inference tax still applied (drains wealth)
- Repeated timeouts lead to bankruptcy

**Verifier Timeout:**
- Result = $\perp$ (undefined)
- No oracle signal, but agents can still trade on validity
- Timeout duration configurable per tournament

**Malformed Agent Response:**
- Cannot parse JSON or invalid structure → forfeit round
- Logged as event, agent warned (optional)

**Whale Bankruptcy:**
- If $W_{whale} < 0.05B$, terminate with error
- Indicates agents collectively exploited market maker
- Rare but valid outcome (exceptional market dynamics)

**System Crash:**
- Market state serialized every N rounds to disk
- Orchestrator can resume from last checkpoint
- Dashboard reconnects to existing orchestrator process

## 6. Theoretical Foundations

### Connection to Logical Induction

Our system implements a **bounded, finite-horizon approximation** of the Logical Induction framework [Garrabrant et al., 2016].

#### **Properties We Satisfy**

**Theorem 1 (Properness):** *The LMSR mechanism is incentive-compatible. Agents maximize expected wealth by reporting true beliefs.*

*Proof:* Follows from Chen & Pennock (2007), Theorem 1. LMSR with logarithmic scoring is strictly proper. □

**Theorem 2 (Deductive Coherence):** *The Whale enforces logical implications between test failures and candidate quality.*

*Formal Statement:* Let $T$ be a test with market validity $p = P_t(\varphi_{V,T})$. If candidate $C$ fails test $T$ while candidate $C'$ passes, the Whale's softmax update enforces:

$$P_{t+1}(\varphi_{G,C}) \leq P_t(\varphi_{G,C}) \cdot \exp(\ln(1-p))$$

*Proof:* The Whale computes $S_C = S_C^{prev} + \ln(1-p)$, then normalizes via softmax. Since $\ln(1-p) < 0$ for $p > 0$, candidate C's unnormalized score decreases, guaranteeing its normalized belief (and thus market price via active trading) decreases. □

*Interpretation:* This ensures observed failures propagate through the belief network, preventing the market from assigning high probability to logically inconsistent states.

**Theorem 3 (Trader Elimination):** *Under inference tax $T_{inf}$ per round, agents with negative expected returns are eliminated in finite time.*

*Formal Statement:* If agent $i$ has expected per-round return $\mathbb{E}[\Delta W_i] < -T_{inf}$, then:
$$\mathbb{P}(\text{agent } i \text{ bankrupt before round } T) \to 1 \text{ as } T \to \infty$$

*Proof Sketch:* Wealth follows biased random walk with negative drift $-T_{inf}$. By optional stopping theorem, probability of hitting zero before time $T$ approaches 1 as $T \to \infty$. □

**Theorem 4 (Convergence Guarantee):** *Total system wealth strictly decreases, guaranteeing eventual termination.*

*Formal Statement:*
$$W_{total,t+1} = W_{total,t} - (m \cdot T_{inf}) < W_{total,t}$$

Since $W_{total,t} \geq 0$ and decreases by at least $m \cdot T_{inf} > 0$ each round:
$$\lim_{t \to \infty} \mathbb{P}(\mathcal{T}(t)) = 1$$

*Interpretation:* The system must eventually terminate. Wealth cannot drain forever.

**Connection to Logical Induction:**

Our system implements a **deductive trader** (Definition 3.2 in Garrabrant et al.):
- The Whale exploits logical inconsistencies (test failure → low quality belief)
- It has sufficient wealth to influence market (though not infinite)
- It cannot be dominated by bounded traders

We also have **inductive traders** (LLM agents):
- Bounded computation (token limits, timeout)
- Search for patterns in code/tests
- Make predictions about unproven statements

#### **Divergences from Full LI**

Our system differs from full Logical Induction in:

1. **Finite Horizon:** We terminate after finite rounds (LI runs forever)
2. **Finite Whale Capital:** Whale has fixed budget $B$ (LI market maker has infinite capital)
3. **Restricted Sentences:** Only test validity + candidate quality (LI handles arbitrary logical sentences)
4. **No Coherence Guarantee:** Master goal prices don't sum to 1 (we use market credences, not formal probabilities)
5. **Modified Market:** LMSR instead of limit order book (see next section)

However, we maintain the **key property**: The market respects computationally verifiable logical constraints via the Whale's deductive enforcement.

### LMSR vs. Logical Induction Market Mechanism

**Garrabrant et al.'s Original Mechanism:**
- Traders submit limit orders (price-quantity pairs)
- Market clears via order matching
- Prices update only when trades execute
- Requires explicit order book management

**Our LMSR Approach:**
- Traders submit beliefs (converted to share purchases)
- Automated market maker always provides liquidity
- Prices update via continuous cost function
- No order book needed

**Why We Chose LMSR:**

1. **Simplicity:** No need to match buyers/sellers; AMM always available
2. **Liquidity:** Whale can always provide counterparty (at current price)
3. **Zero-Sum:** Automatically guaranteed by cost function mathematics
4. **Bounded Loss:** Whale's exposure controllable via dynamic $b_t$
5. **Proper Scoring:** Incentive compatibility proven (Chen & Pennock 2007)
6. **Implementation:** Cleaner code (no order book, no matching algorithm)

**Trade-offs:**
- LMSR prices less granular than order book (single price vs. bid/ask spread)
- LMSR can't express complex order types (limit orders, stop losses)
- LMSR requires liquidity provider (Whale) with sufficient capital
- Dynamic $b$ means liquidity decreases as Whale loses money

For our use case (bounded tournament, known participant set, automatic trading), LMSR is superior.

## Appendices

### Appendix A: LMSR Mathematical Foundations

**Logarithmic Market Scoring Rule (LMSR)** [Hanson 2003, Chen & Pennock 2007]

#### Overview

LMSR is an automated market maker (AMM) that provides continuous liquidity for prediction markets. Unlike traditional order books that require matching buyers and sellers, LMSR allows anyone to trade at any time by transacting with the market maker itself.

#### Basic Setup

**Binary Outcome:** We're betting on whether a statement is true or false
- Outcome space: $\omega \in \{0, 1\}$
- Example: "This test will pass" (1 = passes, 0 = fails)

**Shares:** Traders buy/sell shares that pay out based on the outcome
- **YES shares** pay $\$1$ if outcome is 1, $\$0$ if outcome is 0
- **NO shares** pay $\$1$ if outcome is 0, $\$0$ if outcome is 1

**State Variables:**
- $q_1$: Number of YES shares outstanding (held by all traders combined)
- $q_0$: Number of NO shares outstanding

#### The Cost Function

The heart of LMSR is the cost function that determines prices:

$$C(q_0, q_1) = b \cdot \ln(e^{q_0/b} + e^{q_1/b})$$

**The Liquidity Parameter $b$:**

The parameter $b$ is the single most important tuning knob in LMSR. It controls:

1. **Price Sensitivity:** How much the price moves when someone trades
   - **Low $b$** (e.g., $b = 1$): Prices very sensitive; small trades move market a lot
   - **High $b$** (e.g., $b = 100$): Prices stable; requires large trades to move market
   - **Intuition:** Think of $b$ as "market depth" or "resistance to price change"

2. **Market Maker's Risk:** Maximum amount the market maker can lose
   - **Worst-case loss** = $b \cdot \ln(2) \approx 0.693b$
   - Occurs when market maker is maximally wrong (priced at 50%, outcome at 100%)
   - **Example:** If $b = 100$, max loss is ~$69.3

3. **Subsidy for Information:** How much the system "pays" for price discovery
   - Higher $b$ = more willing to pay traders to reveal information
   - Lower $b$ = cheaper to run but less incentive to trade

**Mathematical Properties:**

The cost function has nice calculus properties:
- **Convex:** Second derivative positive (no arbitrage)
- **Smooth:** Differentiable everywhere (continuous prices)
- **Log-sum-exp form:** Numerically stable (won't overflow)

#### Price Function

The **instantaneous price** is the derivative of the cost function:

$$p_1 = \frac{\partial C}{\partial q_1} = \frac{e^{q_1/b}}{e^{q_0/b} + e^{q_1/b}}$$

**Interpretation:**
- $p_1$ is the market's current probability that outcome will be 1
- Equivalently: cost to buy an infinitesimally small additional YES share
- Always between 0 and 1 (valid probability)

**Symmetry:**
- $p_0 = 1 - p_1$ (NO shares priced complementarily)
- If no shares outstanding ($q_0 = q_1 = 0$), then $p_1 = 0.5$ (neutral)

#### Trading Mechanics

**Executing a Target Wager on YES:**
1. **Agent specifies Wager:** $W_{yes} > 0$
2. **Calculate shares acquired:** Find $\Delta q_{yes}$ such that $C(q_{yes} + \Delta q_{yes}, q_{no}) - C(q_{yes}, q_{no}) = W_{yes}$
3. **Update state:** $q_{yes} \leftarrow q_{yes} + \Delta q_{yes}$

**Executing a Target Wager on NO (Shorting):**
1. **Agent specifies Wager:** $W_{no} > 0$
2. **Calculate shares acquired:** Find $\Delta q_{no}$ such that $C(q_{yes}, q_{no} + \Delta q_{no}) - C(q_{yes}, q_{no}) = W_{no}$
3. **Update state:** $q_{no} \leftarrow q_{no} + \Delta q_{no}$

**Note:** In practice, the system uses Simultaneous Batching to execute all intended wagers for a round concurrently, matching opposing wagers before applying the net remainder to the cost curve (see Section 2.C.4).

#### Final Settlement

When outcome $\omega$ is revealed:

- **If $\omega = 1$:** Every YES share pays $\$1$, NO shares pay $\$0$
- **If $\omega = 0$:** Every NO share pays $\$1$, YES shares pay $\$0$

#### Key Theorems

**Theorem (Chen & Pennock 2007):** LMSR is a **proper scoring rule**
- **Meaning:** An agent maximizes expected profit by reporting their true belief
- **Implication:** No incentive to lie about probabilities
- **Caveat:** Only holds if agent is small relative to market (doesn't move price much)

**Theorem:** LMSR is **zero-sum**
- **Proof:** Total wealth in = cost paid = $C(q_{final}) - C(q_{initial})$
- Total wealth out = $\sum$ (shares × payout) = exactly $C(q_{final}) - C(q_{initial})$
- Therefore: wealth in = wealth out

**Theorem:** Market maker's loss is **bounded**
- **Worst case:** $\max|C| = b \cdot \ln(2) \approx 0.693b$
- **Occurs when:** Market goes from 50-50 to 100-0
- **Interpretation:** Even if completely wrong, max loss is predictable

#### Dynamic Liquidity Parameter

In our system, $b$ is **not constant** but recalculated each round to prevent Whale bankruptcy.

**Formula:**
$$b_t = \max\left(b_{min}, \frac{0.5 \cdot W_{whale,t}}{M_{active,t} \cdot \ln(2)}\right)$$

**Components:**
- $W_{whale,t}$: Whale's current wealth
- $M_{active,t}$: Number of active markets
- $b_{min}$: Minimum liquidity floor (typically $B/200$)
- $\ln(2) \approx 0.693$

**Purpose:**
The numerator $0.5 \cdot W_{whale,t}$ ensures that even if ALL markets move from 50% to 100% simultaneously, the Whale's maximum loss is:
$$L_{max} = M_{active} \cdot b_t \cdot \ln(2) = M_{active} \cdot \frac{0.5 \cdot W_{whale,t}}{M_{active} \cdot \ln(2)} \cdot \ln(2) = 0.5 \cdot W_{whale,t}$$

**Effects:**
- **As Whale wins:** $W_{whale}$ increases → $b$ increases → markets more liquid
- **As Whale loses:** $W_{whale}$ decreases → $b$ decreases → markets less liquid
- **Floor prevents death spiral:** $b_{min}$ ensures markets don't become impossibly illiquid

**Trade-off:**
Lower liquidity means higher price impact per trade. As the Whale loses money, it becomes easier for agents to move prices, but they can extract less total value per round.

### Appendix B: True Kelly Optimization via Convex Programming

The heuristic Kelly approach (Section 2.C.3) is simple but suboptimal. Here's the mathematically rigorous alternative:

**Problem:** Given beliefs $b_j$ and prices $P_j$ for $n$ sentences, find portfolio weights $w_j$ maximizing expected log wealth.

**Objective:**
$$\max_{w} \mathbb{E}[\ln(1 + \sum_j w_j R_j)]$$

where $R_j$ is the random return from sentence $j$.

**Constraints:**
- $\sum_j |w_j| + \sum_{k \in \text{NewProposals}} |w_{bond,k}| \leq 1$ (no leverage)
- $w_j \in [-1, 1]$ (can short)

**Expected Return:**
$$\mathbb{E}[R_j] = b_j \cdot \frac{1-P_j}{P_j} - (1-b_j) \cdot \frac{P_j}{1-P_j}$$

**Approximation (for small $w_j$):**
$$\mathbb{E}[\ln(1 + \sum_j w_j R_j)] \approx \sum_j w_j \mathbb{E}[R_j] - \frac{1}{2}\sum_j w_j^2 \text{Var}(R_j)$$

This becomes a **quadratic program** solvable with convex optimization libraries.

**Advantages over Heuristic:**
- Truly optimal (maximizes $\mathbb{E}[\log W]$)
- Accounts for correlations between bets (if you model covariance properly)
- Respects constraints exactly (no ad-hoc normalization)

**Disadvantages:**
- Requires convex optimization solver (100-1000× slower)
- More complex to implement and debug
- Harder to explain to non-technical audience

**When to Use:**
- **Heuristic:** Real-time trading, need speed, good enough accuracy
- **Optimization:** Post-analysis, backtesting, if accuracy critical

### Appendix C: Alternative Market Mechanisms

We considered several mechanisms before choosing LMSR:

#### **Option 1: Limit Order Book**

**How it works:**
- Traders submit (price, quantity) limit orders
- Orders matched via price-time priority
- Price = last traded price (or midpoint of bid-ask spread)

**Pros:**
- Standard in financial markets
- Precise price discovery (bid-ask spread reveals uncertainty)
- Supports complex order types

**Cons:**
- Requires matching engine (complex algorithm)
- Can have illiquidity problems (no bids/asks at certain prices)
- More complex state management
- Whale needs sophisticated trading strategy

**Why we rejected:** Too complex for our bounded participant set; LMSR's guaranteed liquidity more valuable.

#### **Option 2: Hanson's Original LI Mechanism**

**How it works:**
- Traders submit limit orders
- Market maker provides infinite depth at current belief
- Prices update to maintain "no Dutch book" property

**Pros:**
- Theoretically grounded in original LI paper
- Proven convergence properties

**Cons:**
- Very complex implementation (50+ pages of formalism)
- Requires sophisticated market maker strategy
- Not as clean mathematically as LMSR
- Robin Hanson later developed LMSR as improvement

**Why we rejected:** LMSR is Hanson's cleaned-up, practical version of the LI market mechanism.

### Appendix D: Parameter Tuning Guide

**Critical Parameters:**

| Parameter | Symbol | Recommended Value | Rationale |
|-----------|--------|-------------------|-----------|
| Min Liquidity | $b_{min}$ | $B/200$ | Prevents death spiral while allowing dynamic adjustment |
| Inference Tax | $T_{inf}$ | $0.01 \cdot B/N$ per round | Should eliminate poor traders in ~100 rounds |
| Belief Clip | $\epsilon$ | $0.01$ | Prevents catastrophic losses from overconfidence |
| Bond Lock Period | $N_{lock}$ | 1 round | Long enough to see market reaction, short enough to iterate |
| Max Rounds | $t_{max}$ | 100 | Safety valve; most markets should converge faster |

**Sensitivity Analysis:**

**Minimum Liquidity ($b_{min}$):**
- **Too low** (e.g., $b_{min} = B/1000$): Markets can become impossibly illiquid late in tournament
- **Too high** (e.g., $b_{min} = B/50$): Doesn't prevent Whale bankruptcy if many markets active
- **Rule of thumb:** $b_{min} = B/(2 \times M_{max})$
- **Ensures:** Minimum liquidity allows some trading

**Inference Tax ($T_{inf}$):**
- **Too low** (e.g., $T_{inf} = 0.001 \cdot B/N$): Poor traders survive too long; noise dominates
- **Too high** (e.g., $T_{inf} = 0.1 \cdot B/N$): All agents go bankrupt before finding bugs
- **Target:** Eliminate worst 50% of agents by round 50
- **Adaptive:** Could increase tax over time (accelerate endgame)

**Bond Lock Period ($N_{lock}$):**
- **Too short** (e.g., $N_{lock} = 0$): Can't capture information alpha; proposers exit before market reacts
- **Too long** (e.g., $N_{lock} = 50$): Discourages exploration; capital tied up too long
- **Typical:** 1-5 rounds depending on market speed
- **Adaptive:** Could vary based on sentence type (longer for candidates, shorter for tests)
