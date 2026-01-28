# OpenCode Logical Induction Market: System Specification (v1.0)
==============================================================

**Context:** A resource-competitive software engineering tournament implemented within the `OpenCode` terminal environment. 

<!-- TODO: gemini - Provide a proper link to paper here -->
**Theoretical Foundation:** Computable approximation of _Logical Induction_ (Garrabrant et al., 2016). 

* * *

1\. High-Level Concept & Motivation
-----------------------------------

### The Core Problem

Current Agentic coding systems (like Devin or standard RAG loops) typically rely on a single model checking itself ("Self-Reflection"). This is fragile; models often hallucinate that their own broken code works. Parallel sampling ("Best-of-N") generates many options but lacks a rigorous, automated way to select the winner without expensive human review.

### The Solution: A Logical Market
<!-- TODO: gemini - This section needs a rewrite - explain how it relates to logical inductino and what advantages we may expect -->

We replace the single "Judge" with a **Market**.

<!-- TODO: gemini - this "predict reality" statemetn is vacuous and not informative - give a better explanation - also you need to make it clear that sentance proposal and verifier proposal are key parts of this design - explain how this relates to LI -->
*   **The Incentive:** Agents are not paid to "write code"; they are paid to **predict reality**. 
*   **The Mechanism:** If Agent A writes code, and Agent B finds a test case that breaks it, Agent B captures Agent A's wealth.
*   **The Result:** The system naturally filters out hallucinations because they are "expensive" to maintain against adversarial attacks.

* * *

2\. Operational Workflow (Plain English)
----------------------------------------

### Phase A: Initialization (The Bootstrap)

The system begins when the user provides a prompt  $P_{user}$  and a budget.

1.  **The Goal:** The system registers the Master Sentence  $\varphi _{goal}$ : _"The code satisfies the user's prompt."_
<!-- Lets explain what the baseline agent might be  -->
2.  **The Seed:** A baseline agent generates a "Strawman" code candidate ( $C_{0}$ ). It is likely buggy, but it provides the initial asset for trading.
<!-- What are these M agents? - explain them briefly -->
3.  **The Capital:**  $M$  agents are spawned and initialized with a bankroll of "Compute Credits" ( $W_{0}$ ).

### Phase B: The Trading Round (The "Heartbeat")

The orchestrator runs a discrete loop of **Inference and Trade**:

<!-- Make it clear that agents might not need to recieve a snapshot of market prices or other agents beliefs - whether this is helpful or not would need to be deteriend via experimentation -->
1.  **Observation:** Each agent receives a snapshot of the current market prices ( $P_{t}$ ) and the source code of active candidates.
<!-- Oh - agents definitely need to have a view of sentences for them to communicate their beliefs about sentences -->
<!-- Should agents also recieve the verifiers for sentences? -->
2.  **Inference:** Agents "think" (using Chain-of-Thought) and use local tools (linters, debuggers) to analyze the assets.
<!-- What if an agent failsto report a belief about a sentence? -->
3.  **Belief Formulation:** Based on their analysis, agents form internal probability estimates (e.g., "I am 99% sure Candidate  $C_{0}$  fails on edge case  $X$ ").
4.  **Action:**
<!-- What is the incentive to register new sentences? is thsi something we can realisitcally expect agents to do organically or will they require prompting --> 
<!-- all sentences need to have an associated verifier/oracle -->
<!-- are agents allowed to produce code/ write tests w/o creating sentences? - should the market abitartor automatically create sentences for some actions - e.g. if a test is created it could create  -->
    *   **Propose:** Agents pay a fee to register new sentences (Code or Tests).
    *   **Bet:** Agents submit a **Belief Vector** to the market. Disagreements with the consensus price are treated as implicit bets.
5.  **Market Update:** The Market Maker updates the consensus prices based on the new "Wealth-Weighted" beliefs.
<!-- what about running verifiers? who does that - is it agents or arbitrator or both? -->
<!-- doesn't arbitrator need to arbitarte wealth updates based on verifier results? -->

### Phase C: Settlement (The Oracle)

<!-- Make it clear where the verifiers come from -->
Periodically, the system identifies sentences with **Executable Verifiers** (unit tests).

<!-- what to do for unexecutable verifiers/oracles? - we need to have at least one unverifiable sentence - - which is that the result satisfies user prompt-->
<!-- also what to do w/ verifiers that do not run w/ in certain time/resource constraints -->
1.  **Execution:** The system runs the verified code in a sandbox.
2.  **Payout:** Wealth is redistributed. Agents who correctly predicted the outcome ("Surprised the market") gain wealth; those who were wrong lose it.
3.  **Bankruptcy:** Agents who consistently lose bets or spend too much on inference without return are terminated.

* * *

3\. The Agent as a Session Trace
--------------------------------

<!-- I think this lacks some specificity about how we might actually implement this in opencode -->
In this implementation, an agent is not just a model API call; it is a **Stateful LLM Session**.

*   **Identity:** Each agent persists its "Chain of Thought" history, allowing for multi-step reasoning across market rounds.
*   **The Toolset:**
    *   `read_market_state()`: View prices and code.
    <!-- i think this tool is already part of the opencode framework - we should not reimplemetn this -->
    *   `run_local_tool(cmd)`: Execute private checks (e.g., `python -m py_compile candidate.py`).
    *   `propose_sentence(desc, verifier)`: Register new claims.
    *   `submit_belief(vector)`: Trade on existing claims.

> **Example Trace:**
> 
> *   **Thought:** "The Architect's code for the parser looks correct, but it uses a deprecated library."
> *   **Local Action:** `run_local_tool("pip check candidate_a.py")`  $\to$  `Result: Dependency Error`.
> *   **Proposal:** `propose_sentence("Candidate_A fails dependency check", verifier="assert check_deps()")`.
> *   **Trade:** `submit_belief({"s_goal": 0.1, "s_dep_check": 0.99})` (Shorting the goal, Longing the failure).
>     

* * *

4\. Formal System Specification
-------------------------------

The market is defined as a discrete-time dynamical system  $\Sigma =\left⟨A,\Phi ,W,O\right⟩$ .

*   ** $A$ **: The set of  $m$  Agents.
<!-- Make it clear that each sentence requires a verifier -->
*   ** $\Phi _{t}$ **: The set of active Logical Sentences at round  $t$ .
*   ** $W_{t}\in R_{\ge 0m}$ **: The Wealth Vector (Compute Credits).
<!-- define \perp -->
*   ** $O:\Phi \to {0,1,\perp}$ **: The Oracle function.

### A. The Assets: Sentences & Oracles

Every tradeable asset is a Sentence  $\varphi$ .

<!-- how do we handle verifiers that dont actually verify the sentence? - thsi isn't clear to me -->

<!-- Note that some sentences may have a supposedly computable verifier - but in practice this verifier could be non-computable - maybe infinite looop - maybe resoruce timeout -->
*   **Verifiable Sentences ( $\varphi _{test}$ ):** Possess a computable verifier function  $V_{\varphi }$ . The Oracle  $O\left(\varphi \right)$  is the return value of  $Exec\left(V_{\varphi }\right)$ .
<!-- how do we prevent a glut of unverifiable sentences? - this isn't clear to me - do we let agents propose unverifiable sentences? -->
*   **Unverifiable Sentences ( $\varphi _{goal}$ ):** Do not possess a direct verifier (e.g., "This code is 'good'").  $O\left(\varphi \right)=\perp$  (Undefined).
    *   _Note:_ In v0,  $\varphi _{goal}$  is settled only by proxy (correlation with tests). In v1, this could be settled by a Human Adjudicator.

### B. Consensus Price ( $P_{t}$ )

<!-- Why - does this relate to kelly criterion? - i thin kyou need to explain how we go from beliefe -> kelly bet -> market price -->
<!-- explain relation to logical induction -->
The Market Price is the **Wealth-Weighted Centroid** of agent beliefs. Let  $b_{i,t}$  be the belief vector of agent  $a_{i}$ .

$$
P_{t}\left(\varphi \right)=\frac{\sum_{i=1}^{m} W_{i,t}\cdot b_{i,t}\left(\varphi \right)}{\sum_{i=1}^{m} W_{i,t}}
$$

> **Interpretation:** A "Rich" agent (one with high historical accuracy) moves the market price significantly more than a "Poor" agent.

### C. The Payout (Logarithmic Scoring)
<!-- Why? provide explanatoin for this payout calculation -->
<!-- explain relation to logical induction -->
<!-- how are sentence bets adjudicated in cases where oracles aren't comptjuable or don't finish w/in the time/resource constraints -->
Wealth is updated based on **Information Gain**. The payout  $\Pi _{i,t}$  for agent  $a_{i}$  given Oracle result  $1_{\varphi }$ :

$$
\Pi _{i,t}\left(\varphi \right)=\alpha \cdot W_{i,t}\cdot \left[1_{\varphi }\ln \left(\frac{b_{i,t}\left(\varphi \right)}{P_{t}\left(\varphi \right)}\right)+\left(1-1_{\varphi }\right)\ln \left(\frac{1-b_{i,t}\left(\varphi \right)}{1-P_{t}\left(\varphi \right)}\right)\right]
$$

*   **Implicit Betting:** Agents do not choose stakes. If  $b_{i}\ne P_{t}$ , a bet is automatically placed.
*   **Zero-Sum Logic:** To gain wealth, an agent must **correct** the market. Agreeing with the consensus ( $b_{i}\approx P_{t}$ ) yields  $\Pi \approx 0$ .

### D. Wealth Dynamics
<!-- flesh this sectoin out  -->
<!-- explain relation to logical induction -->

$$
W_{i,t+1}=W_{i,t}+\Pi _{i,t}-Proposal Fees\gamma \cdot N_{props}​​-Inference Cost\lambda \cdot Tokens_{i}​​
$$

* * *

5\. Incentive Dynamics (Why it works)
-------------------------------------
<!-- how do thse properties derive from the lgoical inductoin paper? -->
This formal structure creates specific evolutionary pressures:

1.  **The "Sure-Thing" Sink:**
    *   _Scenario:_ Agent A proposes `assert 1==1`.
    *   _Outcome:_ Everyone agrees ( $b_{i}\approx 1.0$ ). The price  $P\approx 1.0$ . Payout is 0.
    <!-- what is this proposal fee? is this enforced by market adjudicator - doe sthis relate to compute costs? - fine if you dont have an answer - you an list each optoin as a design choice -->
    *   _Result:_ Agent A loses money (the Proposal Fee  $\gamma$ ) for wasting the market's time.
2.  **The "Unverifiable" Lock:**
    *   _Scenario:_ Agent B proposes "Code is elegant" (No Verifier).
    *   _Outcome:_  $O\left(\varphi \right)=\perp$ . The bet never settles.
    *   _Result:_ Agent B's wealth is effectively "frozen" in this belief, unable to generate returns, while their Inference Costs drain them.
3.  **The "Adversarial" Jackpot:**
    *   _Scenario:_ The market is optimistic ( $P\approx 0.9$ ). Agent C finds a "Black Swan" bug and bets  $b_{C}=0.05$ .
    *   _Outcome:_ The test runs and fails ( $1=0$ ).
    *   _Result:_ Agent C captures massive wealth from the optimistic agents. This incentivizes deep, creative testing over superficial agreement.

* * *


<!-- i think this theoretical motivatoin should be placed elsewhere -->
<!-- is there actually much deductoin in this system? I don't think so - the market adjucitaor is not establishing relatoinships b/w sentences  -->
**Theoretical Motivation:** This system is motivated by the _Logical Induction Criterion_, which states that a market of bounded traders will eventually assign probabilities to logical statements that respect the rules of deduction. In software engineering, this means the market will converge on the realization that "If Test A fails, Goal B cannot be True," without needing a human to explicitly program that dependency.

