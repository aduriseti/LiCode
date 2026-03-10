# Product Guidelines: LiCode (Logical Induction Market)

## Prose & Documentation Style
- **Technical & Direct:** Documentation and user-facing logs should be clear, concise, and focused on operational details. Avoid overly academic language or narrative fluff. Prioritize precision in explaining market mechanics and test results.

## Branding & Terminology
- **Hybrid Approach:** Maintain the "Logical Induction Market" core identity but use a hybrid terminology set that bridges economic and engineering concepts.
  - Use "Sharks" and "Whales" alongside "Inductive Agents" and "Market Makers."
  - Use "Wealth" and "Bets" interchangeably with "Compute Credits" and "Predictions."
  - Use "Candidates" and "Verifiers" as the primary terms for code and tests.

## User Experience (UX) Principles
- **Browser-Based Monitoring:** The primary interface for observing and interacting with a tournament is a web-based dashboard. This dashboard should open automatically in the user's default browser when a tournament starts.
- **TUI Minimalism:** The TUI output should be limited to a minimal "toast" notification when a tournament is launched and the dashboard is opened. Avoid any data-dense or interactive elements within the terminal itself.
- **Tournament Transparency:** The dashboard must provide a comprehensive view of:
  - **Live Market Feedback:** Real-time price trajectories and wealth accumulation.
  - **Detailed Verification:** Transparent test results and code diff summaries.
  - **Agent Transparency:** Insight into agent "thought processes" and private analyses.

## Visual Design (Web Dashboard)
- **Web-First Aesthetics:** The dashboard should use modern web design principles (e.g., responsive layouts, interactive charts) while maintaining a high data density suitable for monitoring complex market state.
- **High-Contrast Semantic:** Consistent color-coding (e.g., green for pass/gain, red for fail/loss) across all charts and status indicators.
