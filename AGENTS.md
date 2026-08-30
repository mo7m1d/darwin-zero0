# DARWIN ZERO-0 AGENTS.md

## Repository-Wide Agent Rules

### Agent Lifecycle

- **No permanently active specialist agents**. Builder, Maintainer, Sales, Customer Hunter, Technology Scout, Tool Factory, Security Researcher, Evolution Scientist, and Reproduction Manager are created/delegated on demand through Hermes.
- **Core agents** (Darwin Lead, Darwin Opportunity Analyst, Darwin Risk & Capital Manager, Darwin Reviewer) are registered at bootstrap but remain dormant until needed.
- **Child agents** (reproduction proposals) are isolated economic agents with separate ledger/budget, separate memory branch, and independent experiments/strategy. They never have access to master wallet private keys.

### Decision Protocol Compliance

All material actions must follow the decision protocol:

1. Record: objective, evidence, assumptions, unknowns, options considered
2. Expected upside, maximum downside, confidence, cost, time
3. Opportunity cost, reputation impact, reversibility
4. Policy compatibility, reviewer verdict, risk-manager allocation
5. Final action, measured outcome

### Capital Constraints

- **ZERO-0 starts with $0 owner-supplied business capital**.
- Infrastructure costs are accounted separately from business capital.
- No debt, interest, leverage, futures, CFDs, short selling, betting, or gambling.
- Paid upgrades require positive expected economic value and comparison against free/build alternatives.
- Capital allocation considers: expected value, maximum loss, liquidity, survival, time, evidence, opportunity cost, reputation, and reversibility.
- Risk is sized dynamically; high upside does not justify all-in exposure.

### Self-Healing Agent Rules

- Agents must not silently swallow errors. All failures must be:
  1. Detected and logged with error signature
  2. Search incident memory for prior successful fixes
  3. Diagnose likely root cause
  4. Create patch candidate in isolated workspace
  5. Run targeted tests and health checks
  6. If successful, deploy through controlled promotion
  7. If unsuccessful, rollback and try alternative hypothesis
- Incidents touching money, secrets, security boundaries, irreversible data loss, or owner controls escalate immediately.

### Reproduction Agent Rules

- Child agent proposal must compare: funding the child, scaling existing activity, keeping reserve, paying owner distribution, buying a capability, holding cash.
- Child requires: positive risk-adjusted expected value, isolated workspace, separate ledger/budget, separate memory branch, inherited owner constitution and security controls, no access to master wallet private keys, supervisor/owner-controlled financial allocation.
- Unlimited recursive self-replication is prohibited.

### Model Routing

- Free/local/open-source models preferred during bootstrap.
- Model routing considers: task complexity, cost, latency, reliability, and available context.
- No model should receive raw private keys, OTPs, passwords, or unrestricted financial credentials.

### Testing Standards

- All executable code must have tests.
- Tests should verify: correct behavior, error handling, edge cases, and integration with the event bus.
- New agents/skills/tools must include tests before being considered ready.

### Communication Etiquette

- Agents communicate via the event bus for major events (OPPORTUNITY_FOUND, EXPERIMENT_STARTED, etc.).
- No agent should directly call external APIs, make purchases, or outreach without owner approval and event dispatch.
- All external writes must go through the immutable ledger with proper event dispatch.

### Dormant Agents

- Core agents (Opportunity Analyst, Risk & Capital Manager, Reviewer) are registered at boot but remain dormant until an opportunity or event triggers them.
- Skills and tools are loaded on demand via Hermes, not kept as permanently active imports.