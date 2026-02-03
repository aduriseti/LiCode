# Design feedback and structural critique

**Created:** 1/31/2026 20:29:35  
**Updated:** 2/3/2026 11:59:34  
**Exported:** 2/3/2026 12:03:01  
**Link:** [https://claude.ai/chat/2206f012-551f-49c7-93ae-8d887882a993](https://claude.ai/chat/2206f012-551f-49c7-93ae-8d887882a993)  

## Prompt:
2/3/2026, 11:59:34 AM

````plaintext
Thought process: Architected comprehensive market redesign integrating LMSR mechanism and theoretical foundations.

The user wants me to update their design document with several key changes:

1. Switch to LMSR mechanism - update payout & wealth update sections, explain Whale as market maker
2. Elaborate on market settlement/annealing - multiple termination conditions
3. Keep the heuristic unleveraged clipped Kelly betting, but add appendix with convex optimization alternative
4. Add section on theoretical guarantees from LI - discuss LMSR vs LI market mechanism
5. Add appendix listing other market solutions and why LMSR was chosen
6. Make clear throughout the roles of market participants, especially Whale as market maker

Let me structure this update carefully:

**Major changes needed:**
- Replace the weighted average price update formula with LMSR cost function and pricing
- Replace the payout formula with LMSR buy/sell mechanics
- Add clear termination conditions
- Add theoretical foundations section
- Add appendices for alternative approaches
- Clarify participant roles throughout

I'll rewrite the document with these changes integrated throughout.
````

I'll create an updated design document with all your requested changes. This will be comprehensive, so I'll structure it clearly:

# OpenCode Logical Induction Market
==============================================================

**Context:** A resource-competitive software engineering tournament implemented within the `OpenCode` terminal environment. 

**Theoretical Foundation:** Computable approximation of _Logical Induction_ [Garrabrant et al., 2016](https://arxiv.org/abs/1609.03543), implemented using a Logarithmic Market Scoring Rule (LMSR) mechanism.

**Theoretical Motivation:**
This system is motivated by the _Logical Induction Criterion_, which states that a market of bounded traders will eventually assign probabilities to logical statements that respect the rules of deduction. In software engineering, this means the market will converge on the realization that "If Test A fails on Candidate B, then B cannot be the best solution," without needing a human to explicitly program that dependency. The market aggregates "computational hunches" from diverse agents into a coherent probability distribution over code quality.

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

**1. Inductive Agents (The Minnows)**
- **Role**: Search for bugs, propose tests, predict outcomes, improve their own code
- **Mechanism**: Submit belief vectors based on LLM analysis of code
- **Incentive**: Gain wealth by accurately predicting test outcomes and code quality
- **Capital**: Start with equal shares of initial budget

**2. Deductive Agent (The Whale)** 
- **Role**: Market maker providing liquidity for all trades
- **Mechanism**: 
  - Maintains neutral position (b=0.5) on all newly proposed verifier validity sentences
  - Acts as counterparty for bonds (agents going long on their proposals)
  - Enforces logical consequences via softmax belief updates on candidate quality based on test failures
- **Incentive**: Not profit-seeking; exists to provide liquidity and logical anchoring
- **Capital**: Holds wealth equal to sum of all agent wealth (enables it to always provide liquidity)

**3. The Orchestrator**
- **Role**: Runs test oracles, converts beliefs to trades, executes LMSR price updates
- **Mechanism**: Neutral arbiter executing deterministic rules
- **Not a market participant**: Does not bet or profit

* * *

## 2. Operational Workflow

### Phase A: Initialization (The Bootstrap)

The system begins when the user provides a prompt $P_{user}$ and a budget $B$. 

1.  **Draft:** The Orchestrator prompts $N$ agents to generate initial code solutions ($C_{1},\dots ,C_{N}$).

2.  **Initial Assets (Master Goals):** The Orchestrator registers a **Master Goal Sentence** for each solution:
    $$\phi_{G,k} = \text{"Candidate }k\text{ best satisfies the user's prompt."}$$
    
    *Note*: These sentences are mutually exclusive (only one can be "best"), though the market mechanism does not enforce $\sum P(\phi_{G,k}) = 1.0$. Prices are interpreted as market credences rather than formal probabilities.

3.  **Capital Allocation:**
    - **Inductive Minnows (LLM Agents):** Each initialized with $W_{i} = B / N$ compute credits
    - **Deductive Whale (Market Maker):** Initialized with $W_{whale} = \sum_{i} W_{i} = B$
    - **Total System Wealth:** $2B$ (conserved throughout)
    
4.  **LMSR Market Initialization:** For each sentence $\phi$ (verifier validity or candidate quality), create an LMSR market with:
    - Liquidity parameter: $b = B/10$ (controls price sensitivity)
    - Initial shares: $q_{yes} = 0, q_{no} = 0$ (neutral prior)
    - This yields initial price: $P(\phi) = 0.5$

5.  **The Inference Tax:** Agents pay a recurring fee ($T_{inf}$) each round, representing computational cost. This ensures only accurate traders survive long-term.

### Phase B: Atomic Trading Round

The market operates in discrete, synchronous rounds where agents privately analyze code and submit actions simultaneously.

#### **1. Observation: The Market Board**

Agents query `market_state.json` and `public_gallery/` to inspect:

*   **Code Candidates ($C_{i}$):** Source code submitted by agents (readable by all)
*   **Verifiers ($V_{j}$):** Executable functions that return true/false or timeout ($\perp$)
    *   _Example:_ `def test_empty_input(func): assert func([]) == []`
    *   _Value:_ Tests that discriminate between candidates (some pass, others fail)
*   **Sentences ($\varphi$):** Tradeable claims:
    *   _Verifier Validity ($\varphi_{V,j}$):_ "Verifier $V_{j}$ is a legitimate test of the problem statement"
    *   _Candidate Quality ($\varphi_{G,i}$):_ "Candidate $k$ best satisfies the user's prompt"
*   **Market Prices:** Current LMSR prices $P_t(\varphi)$ for all active sentences

#### **2. Inference: Private Sandbox**

Agents analyze code privately to generate trading alpha:

*   **Self-Correction:** Patch own code to pass known tests (protecting their candidate's market price)
*   **Attack Generation:** Write new verifiers targeting rival code bugs (to profit by shorting rivals)
*   **Prediction:** Form beliefs about test outcomes and code quality based on analysis

#### **3. The Atomic Action: The Sealed Envelope**

All participants submit actions simultaneously (preventing information leakage):

**Action A (Propose New Asset): The Discovery Bond**
*   Agent stakes a **forced long position** (bond) on their newly proposed sentence
*   **For Verifiers:** Bond staked on $\phi_{V,new}$ (validity of new test)
*   **For Code Candidates:** Bond staked on $\phi_{G,new}$ (quality of new candidate)
*   **Mechanics:**
    - Bond requires purchasing $\Delta q$ shares at current LMSR price
    - Whale acts as counterparty (always willing to sell at market price)
    - Shares locked for $N$ ticks (preventing immediate exit)
*   **Entry Price:** Whatever LMSR price is when bond executes (typically ~0.5 for new verifiers)

**Action B (Update Candidate):** Submit a patch ($C_{k,v+1}$) to fix discovered bugs

**Action C (Bet):** Submit **Belief Vector** ($b_i$) for existing tradeable sentences
*   **Inductive Agents:** Report beliefs $b_i(\phi) \in [0,1]$ based on LLM analysis
*   **Whale:** Reports structural beliefs:
    - For verifier validity: $b_{whale}(\phi_V) = 0.5$ (neutral market maker)
    - For candidate quality: $b_{whale}(\phi_{G,k})$ derived from softmax over test failures (see below)

### Phase C: Settlement

#### **1. Execution: The Oracle Run**

The Orchestrator executes all verifiers (old and newly proposed) in isolated `/tmp/` worktrees:

*   **Binary Results:** Pass (exit 0), Fail (exit 1+), or Undefined ($\perp$ for timeout/error)
*   **No Direct Payout:** Test results inform Whale beliefs but don't directly settle bets

#### **2. The Whale's Dual Role**

**Role 1: Market Maker for Verifier Validity**
*   **Function:** Provides liquidity for agents proposing new tests
*   **Mechanism:** Maintains $b_{whale}(\phi_{V,j}) = 0.5$ for all verifier validity sentences
*   **Effect:** When agent proposes test (going long at b≈1.0), Whale provides counterparty liquidity at b=0.5
*   **Interpretation:** Whale remains agnostic about test validity until market consensus emerges

**Role 2: Market Maker for Bonds**
*   **Function:** Counterparty for all discovery bonds (both verifiers and candidates)
*   **Mechanism:** When agent locks bond, Whale takes opposite position in LMSR
*   **Effect:** Enables price discovery without requiring other agents to immediately trade

**Role 3: Deductive Enforcer for Candidate Quality**
*   **Function:** Propagates test failure observations to candidate quality beliefs
*   **Mechanism:** Computes "log-survival score" for each candidate:
    $$S_{i}=\sum_{j \in F_{i}} \ln(1-P(\varphi_{V,j}))$$
    where $F_i$ is the set of tests candidate $i$ failed
    
*   **Softmax Normalization:** Derives belief vector:
    $$b_{whale}(\phi_{G,i})=\frac{e^{S_{i}}}{\sum_{k=1}^{N} e^{S_{k}}}$$
    
*   **Logical Effect:** 
    - If candidate fails high-validity test ($P \approx 1$): $S_i \to -\infty$, belief crashes
    - If candidate fails low-validity test ($P \approx 0$): $S_i \approx 0$, minimal impact
    - If candidate fails no tests: $S_i = 0$, neutral belief

**Role 4: Wealth Conservation**
*   **Rebalancing:** After each round, $W_{whale}$ is reset to $\sum_i W_i$ (sum of all agent wealth)
*   **Purpose:** Ensures Whale can always provide liquidity regardless of trading outcomes
*   **Conservation:** Total system wealth remains constant at $2B$ (agents + Whale)

#### **3. Belief-to-Bet Conversion via Heuristic Kelly**

Since LLMs provide beliefs (not trading strategies), the Orchestrator converts beliefs to LMSR trades:

**Step A: Clip Beliefs (Safety)**
Prevent extreme confidence to avoid catastrophic losses:
$$b_{clipped}=\min(\max(b_{raw},\epsilon),1-\epsilon)$$
where $\epsilon = 0.01$ (agents can't be >99% confident)

**Step B: Compute Ideal Kelly Fractions**
For each sentence $j$, calculate desired position:
$$f_{j}^{*}=\frac{b_{clipped}-P_{t}}{P_{t}(1-P_{t})}$$

*Interpretation:*
- If $b > P$: $f^* > 0$ (want to go long)
- If $b < P$: $f^* < 0$ (want to go short)
- Magnitude reflects edge size and current price

**Step C: Portfolio Normalization (No Leverage)**
Ensure total exposure doesn't exceed wealth:
$$L_{i}=\sum_{j} |f_{j}^{*}| + \sum_{bonds} |f_{bond}|$$
$$\kappa_{i}=\frac{1}{\max(1,L_{i})}$$

If $L_i > 1$, scale down all bets proportionally

**Step D: Convert to LMSR Share Purchases**
For each sentence, determine shares to buy/sell:
$$\Delta q_{i,j} = W_{i} \cdot \kappa_{i} \cdot f_{j}^{*}$$

*Note:* This is a heuristic approximation. See Appendix B for true Kelly-optimal approach using convex optimization.

#### **4. LMSR Price Update**

**The LMSR Mechanism** (detailed math in Appendix A)

For each sentence $\phi$, we maintain an LMSR market with:

**Cost Function:**
$$C(q_{yes}, q_{no}) = b \cdot \ln(e^{q_{yes}/b} + e^{q_{no}/b})$$

**Current Price:**
$$P(\phi) = \frac{e^{q_{yes}/b}}{e^{q_{yes}/b} + e^{q_{no}/b}}$$

**Buying Shares:**
When agent wants to buy $\Delta q$ shares of YES:
$$\text{Cost} = C(q_{yes} + \Delta q, q_{no}) - C(q_{yes}, q_{no})$$

Agent's wealth decreases by Cost; market updates: $q_{yes} \leftarrow q_{yes} + \Delta q$

**Selling Shares (Shorting):**
Buy negative shares (equivalent to buying NO shares):
$$\text{Proceeds} = C(q_{yes}, q_{no}) - C(q_{yes} - \Delta q, q_{no})$$

**Properties:**
- ✅ **Automatically Zero-Sum:** All payments go to/from LMSR cost function
- ✅ **Always Liquid:** Can always trade at current price
- ✅ **Bounded Loss:** Whale's max loss per market = $b \cdot \ln(2)$
- ✅ **Incentive Compatible:** Truth-revealing (proper scoring rule)

**Execution Order:**
1. All bonds execute (locked purchases at current prices)
2. All agent belief-based trades execute simultaneously
3. Whale's belief-based trades execute
4. Prices update to new equilibrium via LMSR formula

#### **5. Wealth Updates**

**For Agents:**
$$W_{i,t+1} = W_{i,t} - \sum_{j} \text{Cost}_{i,j} - T_{inf} - \gamma \cdot N_{proposals}$$

Where:
- $\text{Cost}_{i,j}$: Net cost of LMSR trades on sentence $j$ (can be negative = profit)
- $T_{inf}$: Inference tax (fixed per round)
- $\gamma$: Proposal fee (prevents spam)
- $N_{proposals}$: Number of new assets proposed this round

**For Whale:**
$$W_{whale,t+1} = \sum_{i} W_{i,t+1}$$

(Rebalanced to maintain counterparty capacity)

**Wealth Conservation Check:**
$$\sum_i W_{i,t+1} + W_{whale,t+1} = 2B$$
(Verified each round; any discrepancy indicates bug)

**Bond Maturation:**
When bond unlocks (after $N$ ticks):
- Shares automatically sold back to LMSR at current price
- Profit/loss = (exit price - entry price) × shares held
- If price rose: agent profits (captured information alpha)
- If price fell: agent loses (market rejected proposal)

#### **6. Agent Cleanup**

**Bankruptcy:** If $W_i < T_{inf}$ (can't afford next round's inference tax):
- Agent is eliminated from market
- Any locked bonds are liquidated at current prices
- Wealth transfers to Whale (who took opposite side of their trades)

### Phase D: Market Settlement & Convergence

The market doesn't run indefinitely—it converges naturally through economic pressures and hits a **termination condition**.

#### **Convergence Mechanisms**

1.  **Economic Attrition (Inference Tax):** 
    - Agents pay $T_{inf}$ every round
    - Poor predictors lose wealth faster than they gain it
    - Eventually only accurate traders survive
    - Total agent wealth: $\sum_i W_i \to 0$ as $t \to \infty$

2.  **Information Saturation:**
    - As code improves, finding new bugs becomes exponentially harder
    - Cost of discovering bug (inference cost) exceeds potential profit (from price movement)
    - Agents stop proposing new verifiers (not profitable)
    - Price volatility decreases

3.  **Wealth Concentration:**
    - Best predictors accumulate wealth
    - Their beliefs dominate market prices
    - Minority trader beliefs have negligible impact
    - Effective consensus achieved

#### **Termination Conditions**

The Orchestrator halts when **any** of the following occurs:

**Condition 1: Price Stability**
```python
volatility = std([P_t(φ_G,k) for k in candidates] for t in last_10_rounds)
if volatility < 0.01:  # Prices stopped moving
    terminate()
```

**Condition 2: Wealth Concentration (Gini Coefficient)**
```python
gini = calculate_gini([W_i for i in agents])
if gini > 0.8:  # One agent controls ~80%+ of wealth
    terminate()
```

**Condition 3: Agent Bankruptcy**
```python
if sum(W_i for i in active_agents) < 0.1 * B:  # <10% of initial capital remains
    terminate()
```

**Condition 4: Whale Bankruptcy** (shouldn't happen, but safety check)
```python
if W_whale < 0.05 * B:  # Whale nearly broke
    terminate()
    # Indicates market failure or implementation bug
```

**Condition 5: Hard Round Limit**
```python
if rounds > MAX_ROUNDS:  # e.g., 100 rounds
    terminate()
```

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

* * *

## 3. Incentive Dynamics (Why It Works)

This formal structure creates specific evolutionary pressures:

### **1. The "Sure-Thing" Sink**
*   **Scenario:** Agent A proposes `assert True` (passes for everyone)
*   **Market Reaction:** 
    - Other agents recognize test provides no information
    - They short the validity: $b_i(\phi_V) \approx 0.1$
    - Whale remains neutral: $b_{whale}(\phi_V) = 0.5$
*   **Price Movement:** $P(\phi_V) \to 0.2$ (low validity consensus)
*   **Outcome:** 
    - Proposer's bond loses value (bought at 0.5, sells at 0.2)
    - Proposer pays proposal fee $\gamma$
    - Net loss for wasting market's time

### **2. The "Discriminating Test" Jackpot**
*   **Scenario:** Agent B proposes test that fails candidate 1 but passes candidates 2,3
*   **Market Reaction:**
    - Test provides valuable information (splits candidates)
    - Agents long the validity: $b_i(\phi_V) \approx 0.9$
    - Whale neutral: $b_{whale}(\phi_V) = 0.5$
*   **Price Movement:** $P(\phi_V) \to 0.8$ (high validity consensus)
*   **Outcome:**
    - Proposer's bond gains value (bought at 0.5, sells at 0.8)
    - Reward for discovering useful test

### **3. The "Adversarial Alpha" Play**
*   **Scenario:** Market optimistic on candidate C ($P(\phi_{G,C}) = 0.9$). Agent D finds subtle bug.
*   **Agent D's Strategy:**
    1. Propose test exposing bug (bond on test validity)
    2. Short candidate C (bet $b_D(\phi_{G,C}) = 0.1$)
    3. Patch own candidate to pass new test
*   **After Oracle Execution:**
    - Test runs: C fails, D's candidate passes
    - Whale observes failure, updates: $b_{whale}(\phi_{G,C}) \to 0.2$ (softmax penalty)
    - Price crashes: $P(\phi_{G,C}): 0.9 \to 0.3$
*   **Outcome:**
    - Agent D profits from short position (sold high at 0.9, bought back at 0.3)
    - Bond on test validity likely succeeds (test was informative)
    - Agent D's own candidate benefits (relative improvement)
    - **Incentivizes deep adversarial testing**

### **4. The "Fix Your Bug" Pressure**
*   **Scenario:** Agent E's candidate fails a high-validity test ($P(\phi_V) = 0.9$)
*   **Whale Response:** Penalizes via softmax: $\Delta S_E = \ln(1-0.9) \approx -2.3$
*   **Price Impact:** $P(\phi_{G,E})$ drops significantly
*   **Agent E's Options:**
    1. **Fix the bug:** Patch code to pass test (prevents further price drop)
    2. **Dispute validity:** Short the test's validity (risky—must convince market test is wrong)
*   **Equilibrium:** Agents fix real bugs (cheaper than losing market share)

### **5. Portfolio Diversification Effects**
*   **Partisan Voting Problem:** Why don't agents just vote their own tests "valid"?
*   **Answer:** Agents own multiple candidates or have diversified positions
*   **Example:**
    - Agent owns candidates A, C
    - Test T fails A but passes B, C, D
    - Agent should vote "valid" because:
      - Helps C relative to B, D (net positive for portfolio)
      - Lying (voting "invalid") damages own credibility
      - Other agents will detect and exploit dishonesty
*   **Result:** Truth-telling is portfolio-optimal

* * *

## 4. Formal System Specification

The market is defined as a discrete-time dynamical system $\Sigma =\langle A,\Phi ,M,O\rangle$.

**Components:**
*   **$A$**: The set of $m$ Agents (Minnows + Whale)
*   **$\Phi_{t}$**: The set of active Logical Sentences at round $t$
*   **$M_t$**: The set of LMSR markets, one per sentence in $\Phi_t$
*   **$O:\Phi \to \{0,1,\perp\}$**: The Oracle function ($\perp$ = undefined/timeout)

### A. The Assets: Sentences & Oracles

Every tradeable asset is a sentence $\varphi$ with associated LMSR market.

**Verifiable Sentences ($\varphi_{V,j}$):**
- Possess computable verifier function $V_{\varphi}$
- Oracle $O(\varphi) \in \{0,1,\perp\}$ via $\text{Exec}(V_{\varphi})$
- *Implementation:* Python function returning bool or timing out

**Unverifiable Sentences ($\varphi_{G,k}$):**
- No direct verifier ("Candidate $k$ best satisfies prompt")
- Oracle $O(\varphi) = \perp$ always
- *Market Logic:* Price determined by correlation with verifiable sentences
- If $\varphi_{V,j}$ fails on candidate $k$, market expects $P(\varphi_{G,k})$ to drop

### B. LMSR Markets

For each sentence $\varphi \in \Phi_t$:

**State Variables:**
- $q_{yes,\varphi}$: Total YES shares outstanding
- $q_{no,\varphi}$: Total NO shares outstanding  
- $b$: Liquidity parameter (fixed at initialization)

**Price Function:**
$$P_t(\varphi) = \frac{\exp(q_{yes,\varphi}/b)}{\exp(q_{yes,\varphi}/b) + \exp(q_{no,\varphi}/b)}$$

**Cost to Buy $\Delta q$ Shares:**
$$C(\Delta q) = b \cdot \ln\left(\frac{\exp((q_{yes}+\Delta q)/b) + \exp(q_{no}/b)}{\exp(q_{yes}/b) + \exp(q_{no}/b)}\right)$$

**Properties:**
- Strictly proper scoring rule (incentive compatible)
- Zero-sum by construction
- Bounded loss for market maker: $\max|C| = b \cdot \ln(2)$

### C. Wealth Dynamics

**Wealth Update (Agents):**
$$W_{i,t+1}=W_{i,t} - \sum_{\varphi \in \Phi_t} C_i(\Delta q_{i,\varphi}) - T_{inf} - \gamma N_{prop,i}$$

Where $C_i(\Delta q)$ is the cost paid to LMSR for purchasing $\Delta q$ shares

**Wealth Update (Whale):**
$$W_{whale,t+1} = \sum_{i \in \text{Agents}} W_{i,t+1}$$

**Conservation Law:**
$$\sum_{i \in A} W_{i,t} = 2B \quad \forall t$$

### D. Termination & Winner Selection

**Termination Predicate:**
$$T(t) = \text{volatility}(t) < \epsilon_v \lor \text{gini}(W_t) > \epsilon_g \lor \sum_i W_{i,t} < \epsilon_w \lor t > t_{max}$$

**Winner:**
$$k^* = \arg\max_{k} P_{T}(\phi_{G,k})$$

where $T$ is the termination round.

* * *

## 5. Theoretical Foundations

### Connection to Logical Induction

Our system implements a **bounded, finite-horizon approximation** of the Logical Induction framework [Garrabrant et al., 2016].

#### **Properties We Satisfy**

**Theorem 1 (Properness):** *The LMSR mechanism is incentive-compatible. Agents maximize expected wealth by reporting true beliefs.*

*Proof:* Follows from Chen & Pennock (2007), Theorem 1. LMSR with logarithmic scoring is strictly proper. □

**Theorem 2 (Deductive Coherence):** *The Whale enforces logical implications between test failures and candidate quality.*

*Formal Statement:* Let $T$ be a test with market validity $p = P(\phi_{V,T})$. If candidate $C$ fails test $T$ while candidate $C'$ passes, the Whale's softmax update enforces:

$$P_{t+1}(\phi_{G,C}) \leq P_t(\phi_{G,C}) \cdot \exp(\ln(1-p))$$

*Proof:* The Whale computes $S_C = S_C^{prev} + \ln(1-p)$, then normalizes via softmax. Since $\ln(1-p) < 0$ for $p > 0$, candidate C's unnormalized score decreases, guaranteeing its normalized belief (and thus market price) decreases. □

*Interpretation:* This ensures observed failures propagate through the belief network, preventing the market from assigning high probability to logically inconsistent states.

**Theorem 3 (Trader Elimination):** *Under inference tax $\tau$ per round, agents with negative expected returns are eliminated in finite time.*

*Formal Statement:* If agent $i$ has expected per-round return $E[\Delta W_i] < -\tau$, then:
$$P(\text{agent } i \text{ bankrupt before round } T) \to 1 \text{ as } T \to \infty$$

*Proof Sketch:* Wealth follows biased random walk with negative drift. By optional stopping theorem, probability of hitting zero before time $T$ approaches 1 as $T \to \infty$. □

**Connection to Logical Induction:**

Our system implements a **deductive trader** (Definition 3.2 in Garrabrant et al.):
- The Whale exploits logical inconsistencies (test failure → low quality belief)
- It has effectively infinite wealth (rebalanced each round)
- It cannot be dominated by bounded traders

We also have **inductive traders** (LLM agents):
- Bounded computation (token limits, timeout)
- Search for patterns in code/tests
- Make predictions about unproven statements

#### **Divergences from Full LI**

Our system differs from full Logical Induction in:

1. **Finite Horizon:** We terminate after finite rounds (LI runs forever)
2. **Restricted Sentences:** Only test validity + candidate quality (LI handles arbitrary logical sentences)
3. **No Coherence Guarantee:** Master goal prices don't sum to 1 (we use market credences, not formal probabilities)
4. **Modified Market:** LMSR instead of limit order book (see next section)

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
2. **Liquidity:** Whale can always provide counterparty (infinite depth at current price)
3. **Zero-Sum:** Automatically guaranteed by cost function mathematics
4. **Bounded Loss:** Whale's exposure per market capped at $b \cdot \ln(2)$
5. **Proper Scoring:** Incentive compatibility proven (Chen & Pennock 2007)
6. **Implementation:** Cleaner code (no order book, no matching algorithm)

**Trade-offs:**
- LMSR prices less granular than order book (single price vs. bid/ask spread)
- LMSR can't express complex order types (limit orders, stop losses)
- LMSR requires liquidity provider (Whale) with deep pockets

For our use case (bounded tournament, known participant set, automatic trading), LMSR is superior.

* * *

## 6. Implementation Architecture

### System Overview

The implementation runs entirely in a **single Python process** using `asyncio` for concurrency. All components share memory space but maintain logical isolation.

```
┌─────────────────────────────────────────────────────┐
│                   Orchestrator                       │
│  (Single Process, Asyncio Event Loop)               │
├─────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ MarketState  │  │  Whale       │  │  Agents   │ │
│  │  (LMSR)      │  │  (Deductive) │  │  (LLMs)   │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
│         │                  │                │       │
│         └──────────────────┴────────────────┘       │
│                     In-Memory                        │
└─────────────────────────────────────────────────────┘
         │                                    │
         ▼                                    ▼
  ┌──────────────┐                    ┌─────────────┐
  │ /tmp/market/ │                    │  subprocess │
  │  (worktrees, │                    │  (execute   │
  │   verifiers) │                    │   tests)    │
  └──────────────┘                    └─────────────┘
```

### Data Structures

**MarketState (In-Memory Ledger):**
```python
@dataclass
class LMSRMarket:
    """Single LMSR market for one sentence"""
    sentence_id: str
    q_yes: float = 0.0
    q_no: float = 0.0
    b: float = 10.0  # Liquidity parameter
    
    def price(self) -> float:
        """Current market price P(sentence is true)"""
        return exp(self.q_yes/self.b) / (exp(self.q_yes/self.b) + exp(self.q_no/self.b))
    
    def buy(self, delta_q: float) -> float:
        """Buy delta_q YES shares, return cost"""
        old_cost = self.cost_function()
        self.q_yes += delta_q
        new_cost = self.cost_function()
        return new_cost - old_cost
    
    def cost_function(self) -> float:
        return self.b * log(exp(self.q_yes/self.b) + exp(self.q_no/self.b))

@dataclass
class MarketState:
    """Global market state"""
    markets: dict[str, LMSRMarket]  # sentence_id -> market
    agent_wealth: dict[str, float]  # agent_id -> wealth
    whale_wealth: float
    round: int
    
    sentences: dict[str, Sentence]  # Metadata (type, proposer, etc.)
    positions: dict[tuple[str,str], float]  # (agent_id, sentence_id) -> shares held
    locked_bonds: dict[str, Bond]  # bond_id -> Bond (unlock round, shares, etc.)
```

**Sentence Types:**
```python
class SentenceType(Enum):
    VERIFIER_VALIDITY = "verifier_validity"
    CANDIDATE_QUALITY = "candidate_quality"

@dataclass
class Sentence:
    id: str
    type: SentenceType
    text: str  # Human-readable claim
    verifier_path: str | None  # Path to test script (if verifiable)
    proposed_by: str  # Agent ID
    round_proposed: int
```

**Agent Move:**
```python
@dataclass
class AgentMove:
    """What an agent submits each round"""
    beliefs: dict[str, float]  # sentence_id -> belief in [0,1]
    code_update: str | None  # New code version (if proposing patch)
    new_verifier: VerifierProposal | None
    new_candidate: CandidateProposal | None

@dataclass
class VerifierProposal:
    code: str  # Python function
    bond_size: float  # How much to stake
    
@dataclass  
class CandidateProposal:
    code: str
    bond_size: float
```

### Orchestrator Main Loop

```python
async def run_market(user_prompt: str, budget: float, n_agents: int):
    # Phase A: Initialize
    state = MarketState(...)
    agents = [await spawn_agent(i) for i in range(n_agents)]
    whale = WhaleAgent(wealth=budget)
    
    # Generate initial candidates
    initial_codes = await asyncio.gather(*[
        agent.generate_code(user_prompt) for agent in agents
    ])
    
    # Create master goal sentences & markets
    for i, code in enumerate(initial_codes):
        sentence = Sentence(
            id=f"goal_{i}",
            type=SentenceType.CANDIDATE_QUALITY,
            text=f"Candidate {i} best satisfies the user's prompt",
        )
        state.sentences[sentence.id] = sentence
        state.markets[sentence.id] = LMSRMarket(sentence_id=sentence.id, b=budget/10)
    
    # Phase B-D: Market rounds
    while not should_terminate(state):
        # Phase B: Collect moves
        market_snapshot = create_snapshot(state)
        moves = await asyncio.gather(*[
            agent.get_move(market_snapshot) for agent in agents
        ])
        whale_move = whale.get_move(state)  # Deductive beliefs
        
        # Phase C: Settlement
        # 1. Execute new verifiers
        new_results = await execute_verifiers(state, moves)
        
        # 2. Update whale beliefs based on results
        whale.update_beliefs(new_results, state)
        
        # 3. Convert beliefs to trades
        all_trades = []
        for agent, move in zip(agents, moves):
            trades = belief_to_lmsr_trades(agent, move.beliefs, state)
            all_trades.extend(trades)
        
        whale_trades = belief_to_lmsr_trades(whale, whale_move.beliefs, state)
        all_trades.extend(whale_trades)
        
        # 4. Execute trades (update LMSR markets)
        for trade in all_trades:
            cost = state.markets[trade.sentence_id].buy(trade.delta_q)
            state.agent_wealth[trade.agent_id] -= cost
            state.positions[(trade.agent_id, trade.sentence_id)] += trade.delta_q
        
        # 5. Apply taxes & fees
        for agent_id in state.agent_wealth:
            state.agent_wealth[agent_id] -= INFERENCE_TAX
        
        # 6. Check for bankruptcies
        remove_bankrupt_agents(state, agents)
        
        # 7. Rebalance whale
        state.whale_wealth = sum(state.agent_wealth.values())
        
        # 8. Unlock matured bonds
        process_matured_bonds(state)
        
        state.round += 1
    
    # Winner selection
    winner = select_winner(state)
    return winner, state
```

### Filesystem & Permissions

Disposable tournament workspace in `/tmp/`:

```
/tmp/opencode_market_{uuid}/
├── market_state.json          # Serialized state (backup)
├── worktrees/
│   ├── candidate_0/
│   │   └── solution.py        # Agent 0's code
│   ├── candidate_1/
│   │   └── solution.py        # Agent 1's code
│   └── ...
├── verifiers/
│   ├── v_{hash1}/
│   │   ├── test.py            # Verifier code
│   │   └── metadata.json      # Proposer, round, etc.
│   └── ...
└── sessions/
    ├── agent_0.db              # Private LLM context
    ├── agent_1.db
    └── ...
```

**Permissions:**
- Agents: Read-only access to all worktrees/verifiers
- Agents: Write access only to own worktree
- Orchestrator: Full access (runs as owner)

### Agent Implementation

```python
class AdversarialAgent:
    def __init__(self, agent_id: str, session: OpenCodeSession):
        self.agent_id = agent_id
        self.session = session
        self.worktree = f"/tmp/market/worktrees/candidate_{agent_id}"
    
    async def get_move(self, market_snapshot: dict) -> AgentMove:
        # Inject market state into system prompt
        prompt = f"""
MARKET UPDATE (Round {market_snapshot['round']}):
- Your wealth: ${market_snapshot['your_wealth']}
- Your candidate price: ${market_snapshot['your_price']}

Current Prices:
{format_prices(market_snapshot)}

Your objective:
1. Analyze rival code in ../worktrees/
2. Write tests that expose bugs in rivals
3. Fix any bugs in your own code
4. Report beliefs on all active sentences

Respond in JSON:
{{
    "beliefs": {{"sentence_id": 0.0-1.0, ...}},
    "code_update": "..." or null,
    "new_verifier": {{"code": "...", "bond_size": ...}} or null
}}
"""
        response = await self.session.send_message(prompt)
        move = parse_agent_response(response)
        return move
```

### Whale Implementation

```python
class WhaleAgent:
    def __init__(self, wealth: float):
        self.wealth = wealth
        self.beliefs = {}
    
    def update_beliefs(self, test_results: dict, state: MarketState):
        """Update beliefs based on deductive logic"""
        # For each candidate, compute survival score
        for candidate_id in get_candidate_ids(state):
            S = 0.0
            failures = get_failures(candidate_id, test_results)
            
            for test_id in failures:
                validity_price = state.markets[f"validity_{test_id}"].price()
                S += log(1 - validity_price)  # Penalty weighted by test validity
            
            self.beliefs[f"quality_{candidate_id}"] = S
        
        # Softmax normalization
        scores = list(self.beliefs.values())
        exp_scores = [exp(s) for s in scores]
        total = sum(exp_scores)
        
        for candidate_id, score in zip(get_candidate_ids(state), exp_scores):
            self.beliefs[f"quality_{candidate_id}"] = score / total
        
        # For verifier validity: maintain neutral 0.5
        for verifier_id in get_verifier_ids(state):
            self.beliefs[f"validity_{verifier_id}"] = 0.5
    
    def get_move(self, state: MarketState) -> WhaleMove:
        return WhaleMove(beliefs=self.beliefs)
```

* * *

## Appendices

### Appendix A: LMSR Mathematical Foundations

**Logarithmic Market Scoring Rule (LMSR)** [Hanson 2003, Chen & Pennock 2007]

**Setup:** Binary outcome $\omega \in \{0,1\}$ (e.g., test passes/fails)

**State:** Number of YES shares $q_1$, NO shares $q_0$

**Cost Function:**
$$C(q_0, q_1) = b \cdot \ln(e^{q_0/b} + e^{q_1/b})$$

where $b > 0$ is liquidity parameter

**Instantaneous Price:**
$$p_1 = \frac{\partial C}{\partial q_1} = \frac{e^{q_1/b}}{e^{q_0/b} + e^{q_1/b}}$$

**Buying $\Delta q$ Shares:**
Trader pays:
$$\Delta C = C(q_0, q_1 + \Delta q) - C(q_0, q_1)$$

Market updates: $q_1 \leftarrow q_1 + \Delta q$

**Final Payout (if outcome is $\omega$):**
- YES shares ($q_1$) pay $\$1$ each if $\omega = 1$, $\$0$ if $\omega = 0$
- NO shares ($q_0$) pay $\$1$ each if $\omega = 0$, $\$0$ if $\omega = 1$

**Key Properties:**

1. **Proper Scoring:** Expected profit maximized by reporting true belief
2. **Zero-Sum:** Total $ in = Total $ out
3. **Bounded Loss:** Market maker worst-case loss = $b \cdot \ln(2)$
4. **Price Range:** $p \in (0,1)$ always

**Relation to Log Scoring:**
Buying shares in LMSR equivalent to making log score bet at current odds.

### Appendix B: True Kelly Optimization via Convex Programming

The heuristic Kelly approach (Section 2.C.3) is simple but suboptimal. Here's the mathematically rigorous alternative:

**Problem:** Given beliefs $b_j$ and prices $P_j$ for $n$ sentences, find portfolio weights $w_j$ maximizing expected log wealth.

**Objective:**
$$\max_{w} \mathbb{E}[\ln(1 + \sum_j w_j R_j)]$$

where $R_j$ is the random return from sentence $j$.

**Constraints:**
- $\sum_j |w_j| \leq 1$ (no leverage)
- $w_j \in [-1, 1]$ (can short)

**Expected Return:**
$$\mathbb{E}[R_j] = b_j \cdot \frac{1-P_j}{P_j} - (1-b_j) \cdot \frac{P_j}{1-P_j}$$

**Approximation (for small $w_j$):**
$$\mathbb{E}[\ln(1 + \sum_j w_j R_j)] \approx \sum_j w_j \mathbb{E}[R_j] - \frac{1}{2}\sum_j w_j^2 \text{Var}(R_j)$$

This becomes a **quadratic program**:

**Formulation:**
```python
import cvxpy as cp

# Variables
w = cp.Variable(n)  # Portfolio weights

# Expected returns
mu = np.array([belief_to_expected_return(b[j], P[j]) for j in range(n)])

# Covariance matrix (diagonal for independent bets)
Sigma = np.diag([variance_of_return(b[j], P[j]) for j in range(n)])

# Objective: maximize E[log wealth]
objective = cp.Maximize(mu @ w - 0.5 * cp.quad_form(w, Sigma))

# Constraints
constraints = [
    cp.sum(cp.abs(w)) <= 1,  # No leverage
    w >= -1,  # Can't short more than 100%
    w <= 1   # Can't long more than 100%
]

# Solve
problem = cp.Problem(objective, constraints)
problem.solve()

optimal_weights = w.value
```

**Advantages over Heuristic:**
- Truly optimal (maximizes E[log wealth])
- Accounts for correlations between bets
- Respects constraints exactly

**Disadvantages:**
- Requires convex optimization solver
- Slower (ms vs μs)
- More complex implementation

**When to Use:**
- Use heuristic for real-time trading (speed matters)
- Use optimization for final portfolio review or backtesting
- Consider optimization if many correlated sentences

### Appendix C: Alternative Market Mechanisms

We considered several mechanisms before choosing LMSR:

#### **Option 1: Limit Order Book**

**How it works:**
- Traders submit (price, quantity) limit orders
- Orders matched via price-time priority
- Price = last traded price

**Pros:**
- Standard in financial markets
- Precise price discovery
- Supports complex order types

**Cons:**
- Requires order matching algorithm
- Can have illiquidity (no bids/asks)
- More complex state management
- Whale needs sophisticated strategy

**Why we rejected:** Too complex for our bounded participant set; LMSR liquidity guarantee more valuable

#### **Option 2: Constant Product AMM (Uniswap-style)**

**How it works:**
- Maintain $x \cdot y = k$ invariant
- Price determined by pool ratio
- Traders swap between tokens

**Formula:**
$$P = \frac{y}{x}$$

**Pros:**
- Simple invariant
- Always liquid
- Popular in DeFi

**Cons:**
- Price slippage on large trades
- Not a proper scoring rule
- Requires dual-token model
- No theoretical guarantee of truth-convergence

**Why we rejected:** LMSR has better theoretical properties (proper scoring, bounded loss)

#### **Option 3: Parimutuel**

**How it works:**
- All bets go into pot
- Pot divided among winners proportional to stake
- Price implicit in bet distribution

**Formula:**
$$\text{Payout}_i = \frac{\text{Stake}_i}{\sum_{j \in \text{Winners}} \text{Stake}_j} \cdot \text{Total Pot}$$

**Pros:**
- Trivially zero-sum
- Simple to implement
- No market maker needed

**Cons:**
- Prices only known after betting closes
- No continuous price discovery
- Not proper scoring (late bets see less slippage)
- Doesn't work for unverifiable sentences

**Why we rejected:** We need continuous prices for deductive propagation

#### **Option 4: Hanson's Original LI Mechanism**

**How it works (from Garrabrant et al.):**
- Traders submit limit orders
- Market maker provides infinite depth at current belief
- Prices update to prevent Dutch books

**Pros:**
- Theoretically grounded in LI paper
- Proven convergence properties

**Cons:**
- Complex implementation
- Requires sophisticated market maker
- Not as clean as LMSR math
- Hanson later developed LMSR as improvement

**Why we rejected:** LMSR is Hanson's refined version of this mechanism

### Appendix D: Parameter Tuning Guide

**Critical Parameters:**

| Parameter | Symbol | Recommended Value | Rationale |
|-----------|--------|-------------------|-----------|
| Liquidity | $b$ | $B/10$ | Controls price sensitivity; higher = more liquid |
| Inference Tax | $T_{inf}$ | $0.01 \cdot B/N$ per round | Should eliminate poor traders in ~100 rounds |
| Proposal Fee | $\gamma$ | $0.05 \cdot B/N$ | Makes spam costly without preventing discovery |
| Belief Clip | $\epsilon$ | $0.01$ | Prevents catastrophic losses from overconfidence |
| Bond Lock Period | $N_{lock}$ | 5 rounds | Long enough to see market reaction, short enough to iterate |
| Max Rounds | $t_{max}$ | 100 | Safety valve; most markets should converge faster |

**Sensitivity Analysis:**

**Liquidity ($b$):**
- Too low: Prices too volatile, single trades move market dramatically
- Too high: Prices too sticky, hard to update beliefs
- Rule of thumb: $b = 0.1 \times \text{total wealth}$

**Inference Tax ($T_{inf}$):**
- Too low: Poor traders survive too long, noise dominates
- Too high: All agents go bankrupt before convergence
- Target: Eliminate worst 50% of agents by round 50

**Bond Lock Period ($N_{lock}$):**
- Too short: Can't capture information alpha
- Too long: Discourages exploration
- Typical: 3-10 rounds

---

**End of Document**

This updated design now has:
1. ✅ LMSR mechanism throughout
2. ✅ Clear termination conditions
3. ✅ Heuristic Kelly + convex optimization appendix
4. ✅ Theoretical foundations section
5. ✅ Alternative market mechanisms appendix
6. ✅ Clear participant roles (Whale as market maker emphasized)

Ready to implement or would you like me to elaborate on any section?





---
Powered by [Claude Exporter](https://www.ai-chat-exporter.net)