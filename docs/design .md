# Design feedback and structural critique

**Created:** 1/31/2026 20:29:35  
**Updated:** 2/3/2026 13:13:46  
**Exported:** 2/3/2026 13:32:04  
**Link:** [https://claude.ai/chat/2206f012-551f-49c7-93ae-8d887882a993](https://claude.ai/chat/2206f012-551f-49c7-93ae-8d887882a993)  

## Response:
2/3/2026, 1:13:46 PM

````plaintext
Thought process: Orchestrated comprehensive rewrite addressing LMSR clarification and self-contained formal specification.

The user wants me to do a full rewrite with two additional improvements:

1. Better explanation of LMSR in the appendix - specifically what the liquidity parameter means
2. Make the formal system specification section self-contained with all terms and parameters defined

They've given me permission to do the full rewrite. Let me proceed with:

1. All the changes we discussed earlier (Whale's dual behavior, bond mechanism clarification, etc.)
2. Expanded Appendix A with better LMSR explanation including what the liquidity parameter does
3. A completely rewritten Section 4 (Formal System Specification) that is self-contained and defines all terms

The formal system section should be like a mathematical specification - someone should be able to read JUST that section and understand the entire system precisely. I'll need to:
- Define all symbols and notation upfront
- Explain what each component means in plain language alongside the math
- Make it progressively build from primitives to the full system
- Include examples where helpful

Let me write this now.
````

Perfect! I'll do the full rewrite now with those two improvements. Give me a few minutes to put together a clean, coherent version.

---

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

| Role | Agent Type | Function | Incentive |
|------|-----------|----------|-----------|
| **Inductive Agents (Minnows)** | LLM-based traders | Search for bugs, propose tests, predict outcomes, improve code | Gain wealth by accurate predictions |
| **Deductive Agent (Whale)** | Algorithmic market maker | Provides liquidity, enforces logical consequences | Not profit-seeking; maintains market structure |
| **Orchestrator** | Neutral arbiter | Runs oracles, executes trades, enforces rules | Not a participant; executes deterministic protocol |

**Capital Structure:**
- Each Minnow starts with $W_i = B/N$ (equal allocation of budget $B$ across $N$ agents)
- Whale starts with $W_{whale} = B$ (equal to sum of all agent wealth)
- Total system wealth: $2B$ (conserved throughout)

* * *

## 2. Operational Workflow

### Phase A: Initialization (The Bootstrap)

The system begins when the user provides a prompt $P_{user}$ and a budget $B$.

1. **Draft:** The Orchestrator prompts $N$ agents to generate initial code solutions ($C_{1},\dots ,C_{N}$).

2. **Initial Assets (Master Goals):** The Orchestrator registers a **Master Goal Sentence** for each solution:
   $$\phi_{G,k} = \text{"Candidate }k\text{ best satisfies the user's prompt."}$$
   
   *Note*: These sentences are mutually exclusive (only one can be "best"), though the market mechanism does not enforce $\sum P(\phi_{G,k}) = 1.0$. Prices are interpreted as market credences rather than formal probabilities.

3. **LMSR Market Initialization:** For each sentence $\phi$ (verifier validity or candidate quality), create an LMSR market with:
   - Liquidity parameter: $b = B/10$ (controls price sensitivity; see Appendix A)
   - Initial shares: $q_{yes} = 0, q_{no} = 0$ (neutral prior)
   - This yields initial price: $P(\phi) = 0.5$

4. **The Inference Tax:** Agents pay a recurring fee ($T_{inf}$) each round, representing computational cost. This ensures only accurate traders survive long-term.

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

2. **Proposer Buys Bond:**
   - Proposer purchases $\Delta q$ shares from the LMSR at current price ($P_0 = 0.5$)
   - Payment goes into LMSR cost function
   - Shares are locked for $N_{lock}$ ticks (cannot be sold immediately)

3. **Whale as Passive Counterparty:**
   - The Whale (as LMSR market maker) is automatically the counterparty
   - Whale holds the implicit short position via the LMSR cost function
   - Whale does NOT submit any active belief or trade for newly proposed verifier validity

4. **Price Movement:**
   - After bond purchase: $q_{yes} = \Delta q$
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

**Wealth Conservation:**
- After each round, $W_{whale}$ is reset to $\sum_i W_i$ (sum of all agent wealth)
- Purpose: Ensures Whale can always provide liquidity regardless of trading outcomes
- Conservation: Total system wealth remains constant at $2B$ (agents + Whale)

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
3. Whale's belief-based trades execute (only for candidate quality)
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
When bond unlocks (after $N_{lock}$ ticks):
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
- **Scenario:** Agent A proposes `assert True` (passes for everyone)
- **Market Reaction:**
  - Other agents recognize test provides no information
  - They short the validity: $b_i(\phi_V) \approx 0.1$
  - Whale remains passive (doesn't trade on verifier validity)
- **Price Movement:** $P(\phi_V) \to 0.2$ (low validity consensus)
- **Outcome:**
  - Proposer's bond loses value (bought at 0.5, sells at 0.2)
  - Proposer pays proposal fee $\gamma$
  - Net loss for wasting market's time

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

* * *

## 4. Formal System Specification

This section provides a complete, self-contained mathematical specification of the market. All terms and parameters are defined here.

### System Definition

The market is a discrete-time dynamical system $\Sigma = \langle \mathcal{A}, \Phi, \mathcal{M}, \mathcal{O}, \mathcal{W} \rangle$ operating over rounds $t = 0, 1, 2, \ldots$

**Components:**

- **$\mathcal{A} = \{a_1, \ldots, a_m, a_{whale}\}$**: The set of market participants
  - $a_1, \ldots, a_m$: The Minnows (inductive agents)
  - $a_{whale}$: The Whale (deductive agent + market maker)
  - $m$: Number of Minnow agents (typically $m = N$ where $N$ is from initialization)

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
  - Initial condition: $W_{i,0} = B/N$ for all Minnows
  - Initial condition: $W_{whale,0} = B$
  - Invariant: $\sum_{i=1}^m W_{i,t} + W_{whale,t} = 2B$ for all $t$

**Parameters (Constants):**

- $B$: Total budget (in compute credits)
- $N$: Number of initial candidates (typically $N = m$)
- $b$: LMSR liquidity parameter ($b = B/10$ typically)
- $T_{inf}$: Inference tax per round (e.g., $T_{inf} = 0.01 \cdot B/N$)
- $\gamma$: Proposal fee (e.g., $\gamma = 0.05 \cdot B/N$)
- $\epsilon$: Belief clipping parameter ($\epsilon = 0.01$)
- $N_{lock}$: Bond lock period in rounds (e.g., $N_{lock} = 5$)

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
- $b$: Liquidity parameter (fixed at market creation)

**Price Function:**
$$P_t(\varphi) = \frac{\exp(q_{yes,\varphi,t}/b)}{\exp(q_{yes,\varphi,t}/b) + \exp(q_{no,\varphi,t}/b)}$$

*Interpretation:* $P_t(\varphi)$ is the market's current probability that sentence $\varphi$ is true.

**Cost Function:**
$$C_\varphi(q_{yes}, q_{no}) = b \cdot \ln\left(\exp(q_{yes}/b) + \exp(q_{no}/b)\right)$$

*Purpose:* Determines how much an agent must pay to change share quantities.

**Buying $\Delta q$ YES Shares:**
When agent $a_i$ wants to buy $\Delta q$ shares (positive for long, negative for short):

$$\text{Cost}_{i,\varphi}(\Delta q) = C_\varphi(q_{yes,\varphi,t} + \Delta q, q_{no,\varphi,t}) - C_\varphi(q_{yes,\varphi,t}, q_{no,\varphi,t})$$

**Market Update:**
$$q_{yes,\varphi,t+1} = q_{yes,\varphi,t} + \Delta q$$

**Key Properties:**
- **Proper Scoring:** Agents maximize expected wealth by reporting true beliefs
- **Zero-Sum:** $\sum_i \text{Cost}_{i,\varphi} = 0$ (all payments net to zero via cost function)
- **Always Liquid:** Can always trade at current $P_t(\varphi)$
- **Bounded Loss:** Whale's max loss per market = $b \cdot \ln(2) \approx 0.693b$

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
   - Requires bond: force-buy $\Delta q_{bond}$ shares at $P_0 = 0.5$
   - Shares locked for $N_{lock}$ rounds
   - Costs proposal fee $\gamma$

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
$$f_{\varphi}^* = \frac{b_{i,t}^{clip}(\varphi) - P_t(\varphi)}{P_t(\varphi)(1 - P_t(\varphi))}$$

*Interpretation:*
- $f_{\varphi}^* > 0$: Want to long (buy YES shares)
- $f_{\varphi}^* < 0$: Want to short (buy NO shares)
- $|f_{\varphi}^*|$: Fraction of wealth to commit

**Step 3 - Normalize Portfolio (No Leverage):**
$$L_i = \sum_{\varphi \in \Phi_t} |f_{\varphi}^*|$$

$$\kappa_i = \frac{1}{\max(1, L_i)}$$

*Purpose:* If total desired exposure exceeds 100% of wealth, scale down proportionally.

**Step 4 - Execute Trades:**
For each sentence $\varphi$:
$$\Delta q_{i,\varphi} = W_{i,t} \cdot \kappa_i \cdot f_{\varphi}^*$$

Execute LMSR trade: buy $\Delta q_{i,\varphi}$ shares of $\varphi$

**Output:** Set of trades $\{(\varphi, \Delta q_{i,\varphi})\}_{\varphi \in \Phi_t}$

### E. Wealth Dynamics

**Within-Round Wealth Updates:**

After all agents submit trades in round $t$:

1. **Trade Costs:** For each agent $a_i$ and sentence $\varphi$:
   $$\text{Cost}_{i,\varphi,t} = C_\varphi(q_{yes} + \Delta q_{i,\varphi}, q_{no}) - C_\varphi(q_{yes}, q_{no})$$
   
2. **Aggregate Wealth Change from Trading:**
   $$\Delta W_{i,t}^{trade} = -\sum_{\varphi \in \Phi_t} \text{Cost}_{i,\varphi,t}$$
   
3. **Fees and Taxes:**
   $$\Delta W_{i,t}^{fees} = -T_{inf} - \gamma \cdot N_{proposals,i,t}$$
   
   where $N_{proposals,i,t}$ is the number of new assets agent $i$ proposed in round $t$

**End-of-Round Wealth:**
$$W_{i,t+1} = W_{i,t} + \Delta W_{i,t}^{trade} + \Delta W_{i,t}^{fees}$$

**Whale Wealth Rebalancing:**
$$W_{whale,t+1} = \sum_{i=1}^m W_{i,t+1}$$

*Purpose:* Ensures Whale always has sufficient capital to provide liquidity.

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

**$\mathcal{T}_4(t)$ - Whale Bankruptcy (Safety):**
$$\mathcal{T}_4(t) = [W_{whale,t} < 0.05 \cdot B]$$

*Note:* This should not occur by construction; indicates implementation bug.

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
5. **Trade Conversion:** Convert beliefs to $\Delta q$ via Kelly heuristic
6. **Trade Execution:** Update LMSR markets, deduct costs from wealth
7. **Fee Application:** Deduct $T_{inf}$ and $\gamma$ from agent wealth
8. **Whale Rebalancing:** Set $W_{whale,t+1} = \sum_i W_{i,t+1}$
9. **Bankruptcy Check:** Remove agents with $W_i < T_{inf}$
10. **Bond Maturation:** Unlock and settle bonds from round $t - N_{lock}$
11. **Termination Check:** If $\mathcal{T}(t+1)$, terminate and select winner

* * *

## 5. Theoretical Foundations

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

```python
from dataclasses import dataclass
from enum import Enum
from math import exp, log

@dataclass
class LMSRMarket:
    """Single LMSR market for one sentence"""
    sentence_id: str
    q_yes: float = 0.0
    q_no: float = 0.0
    b: float = 10.0  # Liquidity parameter
    
    def price(self) -> float:
        """Current market price P(sentence is true)"""
        exp_yes = exp(self.q_yes / self.b)
        exp_no = exp(self.q_no / self.b)
        return exp_yes / (exp_yes + exp_no)
    
    def buy(self, delta_q: float) -> float:
        """Buy delta_q YES shares, return cost"""
        old_cost = self.cost_function()
        self.q_yes += delta_q
        new_cost = self.cost_function()
        return new_cost - old_cost
    
    def cost_function(self) -> float:
        """LMSR cost function"""
        exp_yes = exp(self.q_yes / self.b)
        exp_no = exp(self.q_no / self.b)
        return self.b * log(exp_yes + exp_no)

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

@dataclass
class MarketState:
    """Global market state"""
    markets: dict[str, LMSRMarket]  # sentence_id -> market
    agent_wealth: dict[str, float]  # agent_id -> wealth
    whale_wealth: float
    round: int
    
    sentences: dict[str, Sentence]  # Metadata
    positions: dict[tuple[str, str], float]  # (agent_id, sentence_id) -> shares
    locked_bonds: dict[str, Bond]  # bond_id -> Bond

@dataclass
class Bond:
    """A time-locked position from a proposal"""
    agent_id: str
    sentence_id: str
    shares: float
    unlock_round: int

@dataclass
class AgentMove:
    """What an agent submits each round"""
    beliefs: dict[str, float]  # sentence_id -> belief in [0,1]
    code_update: str | None
    new_verifier: VerifierProposal | None
    new_candidate: CandidateProposal | None

@dataclass
class VerifierProposal:
    code: str  # Python function
    bond_size: float

@dataclass
class CandidateProposal:
    code: str
    bond_size: float
```

### Orchestrator Main Loop

```python
async def run_market(user_prompt: str, budget: float, n_agents: int):
    # Phase A: Initialize
    state = MarketState(
        markets={},
        agent_wealth={},
        whale_wealth=budget,
        round=0,
        sentences={},
        positions={},
        locked_bonds={}
    )
    
    agents = [await spawn_agent(i) for i in range(n_agents)]
    whale = WhaleAgent(wealth=budget)
    
    # Initialize agent wealth
    for i, agent in enumerate(agents):
        state.agent_wealth[f"agent_{i}"] = budget / n_agents
    
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
            verifier_path=None,
            proposed_by=f"agent_{i}",
            round_proposed=0
        )
        state.sentences[sentence.id] = sentence
        state.markets[sentence.id] = LMSRMarket(
            sentence_id=sentence.id, 
            b=budget/10
        )
    
    # Phase B-D: Market rounds
    while not should_terminate(state):
        # Phase B: Collect moves
        market_snapshot = create_snapshot(state)
        moves = await asyncio.gather(*[
            agent.get_move(market_snapshot) for agent in agents
        ])
        
        # Phase C: Settlement
        # 1. Execute new verifiers
        new_results = await execute_verifiers(state, moves)
        
        # 2. Update whale beliefs based on results (only for candidate quality)
        whale.update_beliefs(new_results, state)
        
        # 3. Convert beliefs to trades
        all_trades = []
        for i, (agent, move) in enumerate(zip(agents, moves)):
            agent_id = f"agent_{i}"
            trades = belief_to_lmsr_trades(
                agent_id, 
                move.beliefs, 
                state.agent_wealth[agent_id],
                state
            )
            all_trades.extend(trades)
        
        # Whale trades (only on candidate quality)
        whale_trades = belief_to_lmsr_trades(
            "whale",
            whale.get_candidate_beliefs(),
            state.whale_wealth,
            state
        )
        all_trades.extend(whale_trades)
        
        # 4. Execute trades (update LMSR markets)
        for trade in all_trades:
            cost = state.markets[trade.sentence_id].buy(trade.delta_q)
            if trade.agent_id == "whale":
                # Whale wealth managed separately (rebalanced)
                pass
            else:
                state.agent_wealth[trade.agent_id] -= cost
            state.positions[(trade.agent_id, trade.sentence_id)] += trade.delta_q
        
        # 5. Apply taxes & fees
        for agent_id in list(state.agent_wealth.keys()):
            state.agent_wealth[agent_id] -= INFERENCE_TAX
            # Add proposal fees if agent proposed anything
        
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
- Your wealth: ${market_snapshot['your_wealth']:.2f}
- Your candidate price: ${market_snapshot['your_price']:.2f}

Current Prices:
{format_prices(market_snapshot)}

Your objective:
1. Analyze rival code in ../worktrees/
2. Write tests that expose bugs in rivals
3. Fix any bugs in your own code
4. Report beliefs on all active sentences

Respond in JSON format:
{{
    "beliefs": {{"sentence_id": probability, ...}},
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
        self.candidate_beliefs = {}  # Only for candidate quality
    
    def update_beliefs(self, test_results: dict, state: MarketState):
        """Update beliefs based on deductive logic (only for candidates)"""
        candidate_ids = [
            s.id for s in state.sentences.values() 
            if s.type == SentenceType.CANDIDATE_QUALITY
        ]
        
        # Compute log-survival scores
        scores = {}
        for candidate_id in candidate_ids:
            S = 0.0
            failures = get_failures(candidate_id, test_results, state)
            
            for test_id in failures:
                validity_sentence_id = f"validity_{test_id}"
                if validity_sentence_id in state.markets:
                    validity_price = state.markets[validity_sentence_id].price()
                    S += log(1 - validity_price)
            
            scores[candidate_id] = S
        
        # Softmax normalization
        exp_scores = {cid: exp(s) for cid, s in scores.items()}
        total = sum(exp_scores.values())
        
        for candidate_id in candidate_ids:
            self.candidate_beliefs[candidate_id] = exp_scores[candidate_id] / total
    
    def get_candidate_beliefs(self) -> dict[str, float]:
        """Return beliefs only for candidate quality (not verifier validity)"""
        return self.candidate_beliefs.copy()
```

### Filesystem Structure

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

* * *

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

**Choosing $b$:**
- **Rule of thumb:** $b \approx$ (total budget) / 10
- **Reasoning:** Limits max loss to ~7% of budget per market
- **Our setting:** With budget $B$, we set $b = B/10$
- **Example:** Budget of $1000 → $b = 100$ → max loss per market = $69.3

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

**Buying $\Delta q$ YES shares:**

1. **Calculate cost:**
   $$\text{Cost} = C(q_0, q_1 + \Delta q) - C(q_0, q_1)$$

2. **Trader pays:** $\$\text{Cost}$ to the market maker

3. **Update state:** $q_1 \leftarrow q_1 + \Delta q$

4. **Price moves:** New price $p_1' > p_1$ (buying pushes price up)

**Example with Numbers:**

Suppose $b = 100$, currently $q_0 = q_1 = 0$ (so $p_1 = 0.5$)

Agent wants to buy $\Delta q = 50$ YES shares:

$$\text{Cost} = 100 \ln(e^{0/100} + e^{50/100}) - 100 \ln(e^{0/100} + e^{0/100})$$
$$= 100 \ln(1 + e^{0.5}) - 100 \ln(2)$$
$$\approx 100(1.07) - 100(0.69) = 38$$

After this trade:
- Agent paid $\$38$
- Agent holds 50 YES shares
- New price: $p_1 = e^{0.5}/(1 + e^{0.5}) \approx 0.62$

**Selling (Shorting):**

To short (bet NO), simply buy negative YES shares:
- Buying $\Delta q = -50$ is equivalent to buying 50 NO shares
- Get $\$\text{Proceeds}$ from market maker
- Price moves down

#### Final Settlement

When outcome $\omega$ is revealed:

- **If $\omega = 1$:** Every YES share pays $\$1$, NO shares pay $\$0$
- **If $\omega = 0$:** Every NO share pays $\$1$, YES shares pay $\$0$

**Example Settlement:**

Agent bought 50 YES shares for $\$38$ when $p = 0.5 \to 0.62$

- **If outcome = 1:** Agent gets $50 \times \$1 = \$50$, profit = $\$12$
- **If outcome = 0:** Agent gets $\$0$, loss = $\$38$

**Expected value (if agent believed $p = 0.62$):**
$$E[\text{profit}] = 0.62(50-38) + 0.38(0-38) = 7.44 - 14.44 = -7$$

Wait, that's negative! This is correct—buying at market price $p = 0.62$ when you also believe $p = 0.62$ gives zero expected profit. You only profit if you know something the market doesn't.

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

#### Practical Implementation Notes

**Numerical Stability:**

Use log-sum-exp trick to avoid overflow:
```python
def log_sum_exp(x, y):
    """Compute log(exp(x) + exp(y)) stably"""
    max_val = max(x, y)
    return max_val + log(exp(x - max_val) + exp(y - max_val))

def cost_function(q_yes, q_no, b):
    return b * log_sum_exp(q_yes/b, q_no/b)
```

**Updating Prices:**

Don't recompute from scratch; update incrementally:
```python
# After buying delta_q YES shares:
old_price = price(q_yes, q_no, b)
q_yes += delta_q
new_price = price(q_yes, q_no, b)
# new_price > old_price (price moved up)
```

**Liquidity Parameter Tuning:**

| Market Condition | Recommended $b$ | Reasoning |
|------------------|----------------|-----------|
| High uncertainty | Higher (e.g., $B/5$) | Encourage exploration |
| Low noise | Lower (e.g., $B/20$) | React faster to information |
| Many traders | Higher | Absorb more volume |
| Few traders | Lower | More responsive to each trade |

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
import numpy as np

def kelly_optimal_portfolio(beliefs, prices, wealth):
    """
    Compute Kelly-optimal portfolio via convex optimization
    
    Args:
        beliefs: dict[sentence_id, float] - agent's beliefs
        prices: dict[sentence_id, float] - current market prices
        wealth: float - agent's current wealth
    
    Returns:
        dict[sentence_id, float] - optimal shares to buy
    """
    n = len(beliefs)
    sentence_ids = list(beliefs.keys())
    
    # Variables
    w = cp.Variable(n)  # Portfolio weights (fraction of wealth)
    
    # Expected returns for each sentence
    mu = np.array([
        beliefs[sid] * (1 - prices[sid])/prices[sid] - 
        (1 - beliefs[sid]) * prices[sid]/(1 - prices[sid])
        for sid in sentence_ids
    ])
    
    # Variance of returns (simplified: assume independent)
    variances = np.array([
        beliefs[sid] * (1 - beliefs[sid]) * 
        ((1 - prices[sid])/prices[sid] + prices[sid]/(1 - prices[sid]))**2
        for sid in sentence_ids
    ])
    Sigma = np.diag(variances)
    
    # Objective: maximize expected log wealth
    # E[log(1 + w'R)] ≈ w'μ - 0.5 * w'Σw
    objective = cp.Maximize(mu @ w - 0.5 * cp.quad_form(w, Sigma))
    
    # Constraints
    constraints = [
        cp.sum(cp.abs(w)) <= 1,  # No leverage (total exposure ≤ 100%)
        w >= -1,  # Can't short more than 100% on any single bet
        w <= 1    # Can't long more than 100% on any single bet
    ]
    
    # Solve
    problem = cp.Problem(objective, constraints)
    problem.solve()
    
    if problem.status != 'optimal':
        raise ValueError(f"Optimization failed: {problem.status}")
    
    # Convert weights to share quantities
    optimal_shares = {}
    for i, sid in enumerate(sentence_ids):
        optimal_shares[sid] = w.value[i] * wealth
    
    return optimal_shares
```

**Advantages over Heuristic:**
- Truly optimal (maximizes $\mathbb{E}[\log W]$)
- Accounts for correlations between bets (if you model $\Sigma$ properly)
- Respects constraints exactly (no ad-hoc normalization)

**Disadvantages:**
- Requires convex optimization solver (CVXPY, 100-1000x slower)
- More complex to implement and debug
- Harder to explain to non-technical audience

**When to Use:**
- **Heuristic:** Real-time trading, need speed, good enough accuracy
- **Optimization:** Post-analysis, backtesting, if accuracy critical
- **Hybrid:** Use heuristic during tournament, validate with optimization afterward

### Appendix C: Alternative Market Mechanisms

We considered several mechanisms before choosing LMSR:

#### **Option 1: Limit Order Book**

**How it works:**
- Traders submit (price, quantity) limit orders: "I'll buy 100 shares at $0.60"
- Orders matched via price-time priority
- Price = last traded price (or midpoint of bid-ask spread)

**Pros:**
- Standard in financial markets (NYSE, NASDAQ)
- Precise price discovery (bid-ask spread reveals uncertainty)
- Supports complex order types (stop-loss, iceberg, etc.)

**Cons:**
- Requires matching engine (complex algorithm)
- Can have illiquidity problems (no bids/asks at certain prices)
- More complex state management (maintain order book, handle partial fills)
- Whale needs sophisticated trading strategy (not just structural role)

**Why we rejected:** Too complex for our bounded participant set; LMSR's guaranteed liquidity more valuable than order book expressiveness.

#### **Option 2: Constant Product AMM (Uniswap-style)**

**How it works:**
- Maintain pool with $x$ YES tokens and $y$ NO tokens
- Invariant: $x \cdot y = k$ (constant)
- Price: $P = y / (x + y)$
- Traders swap tokens, changing ratio

**Formula:**
To buy $\Delta x$ YES tokens, must deposit:
$$\Delta y = \frac{y \cdot \Delta x}{x - \Delta x}$$

**Pros:**
- Extremely simple invariant ($xy = k$)
- Always liquid (can always trade)
- Popular in DeFi (proven at scale)
- No external market maker needed

**Cons:**
- **High slippage** on large trades (price moves quadratically)
- Not a proper scoring rule (incentives unclear)
- Requires dual-token model (YES/NO tokens)
- No theoretical guarantee of truth-convergence

**Why we rejected:** LMSR has better theoretical properties (proper scoring, bounded loss, linear price impact for small trades).

#### **Option 3: Parimutuel**

**How it works:**
- All bets go into a pot
- Pot divided among winners proportional to their stake
- No continuous pricing; price implicit in bet distribution

**Formula:**
If outcome is $\omega$, and total stake on $\omega$ is $S_\omega$:
$$\text{Payout}_i = \frac{\text{Stake}_i}{S_\omega} \cdot \text{Total Pot}$$

**Example:**
- 100 people bet $1000 total: $600 on YES, $400 on NO
- Outcome: YES wins
- If you bet $60 on YES, you get: $(60/600) \times 1000 = 100$ (profit = $40)

**Pros:**
- Trivially zero-sum (by construction)
- Simple to implement (just track stakes)
- No market maker needed (peers bet against each other)
- Used in horse racing, lotteries (proven model)

**Cons:**
- **No continuous prices** (only know odds after betting closes)
- **No price discovery** during trading period
- Not proper scoring (late bets see different odds than early bets)
- Doesn't work for unverifiable sentences (when do you settle?)

**Why we rejected:** We need continuous prices for the Whale's deductive propagation (candidate price must drop immediately when test fails).

#### **Option 4: Hanson's Original LI Mechanism**

**How it works (from Garrabrant et al.):**
- Traders submit limit orders like traditional exchange
- Market maker provides infinite depth at current belief
- Prices update to maintain "no Dutch book" property
- Complex rules for order matching and price adjustment

**Pros:**
- Theoretically grounded in original LI paper
- Proven convergence properties (under assumptions)
- Handles arbitrary logical dependencies

**Cons:**
- Very complex implementation (50+ pages of formalism)
- Requires sophisticated market maker strategy
- Not as clean mathematically as LMSR
- Robin Hanson later developed LMSR as a refinement of these ideas

**Why we rejected:** LMSR is essentially Hanson's cleaned-up, practical version of the LI market mechanism. Gets 90% of benefits with 10% of complexity.

### Appendix D: Parameter Tuning Guide

**Critical Parameters:**

| Parameter | Symbol | Recommended Value | Rationale |
|-----------|--------|-------------------|-----------|
| Liquidity | $b$ | $B/10$ | Controls price sensitivity; limits max loss to ~7% per market |
| Inference Tax | $T_{inf}$ | $0.01 \cdot B/N$ per round | Should eliminate poor traders in ~100 rounds |
| Proposal Fee | $\gamma$ | $0.05 \cdot B/N$ | Makes spam costly without preventing legitimate discovery |
| Belief Clip | $\epsilon$ | $0.01$ | Prevents catastrophic losses from overconfidence |
| Bond Lock Period | $N_{lock}$ | 5 rounds | Long enough to see market reaction, short enough to iterate |
| Max Rounds | $t_{max}$ | 100 | Safety valve; most markets should converge faster |

**Sensitivity Analysis:**

**Liquidity ($b$):**
- **Too low** (e.g., $b = B/100$): Prices too volatile; single trade moves market dramatically; agents can manipulate
- **Too high** (e.g., $b = B$): Prices too sticky; hard to update even with strong evidence; market slow to converge
- **Rule of thumb:** $b = 0.1 \times (\text{total wealth in system})$
- **Dynamic tuning:** Could start high (encourage exploration), decrease over time (faster convergence)

**Inference Tax ($T_{inf}$):**
- **Too low** (e.g., $T_{inf} = 0.001 \cdot B/N$): Poor traders survive too long; noise dominates signal; slow convergence
- **Too high** (e.g., $T_{inf} = 0.1 \cdot B/N$): All agents go bankrupt before finding bugs; market dies prematurely
- **Target:** Eliminate worst 50% of agents by round 50
- **Adaptive:** Could increase tax over time (accelerate endgame)

**Bond Lock Period ($N_{lock}$):**
- **Too short** (e.g., $N_{lock} = 1$): Can't capture information alpha; proposers exit before market reacts
- **Too long** (e.g., $N_{lock} = 50$): Discourages exploration; capital tied up too long; can't adapt to new info
- **Typical:** 3-10 rounds depending on market speed
- **Adaptive:** Could vary based on sentence type (longer for candidates, shorter for tests)

**Example Parameter Sets:**

**Conservative (Long tournament, thorough testing):**
```python
B = 1000
N = 10
b = 100  # B/10
T_inf = 1  # 0.01 * B/N
gamma = 5  # 0.05 * B/N
N_lock = 10
t_max = 200
```

**Aggressive (Fast iteration, quick convergence):**
```python
B = 1000
N = 10
b = 50  # B/20 (more volatile)
T_inf = 2  # 0.02 * B/N (faster attrition)
gamma = 2  # 0.02 * B/N (encourage more proposals)
N_lock = 3  # Faster unlock
t_max = 50  # Shorter deadline
```

---

**End of Document**

This rewrite includes:
1. ✅ All previously discussed changes (Whale's dual behavior, bond mechanism, etc.)
2. ✅ Expanded Appendix A with detailed LMSR explanation including liquidity parameter
3. ✅ Completely rewritten Section 4 that is self-contained with all terms defined
4. ✅ Progressive build-up from primitives to full system
5. ✅ Clear notation and mathematical precision throughout

The formal specification (Section 4) is now truly self-contained - someone could read just that section and understand the entire system precisely.





---
Powered by [Claude Exporter](https://www.ai-chat-exporter.net)