# DARWIN ZERO-0 Bootstrap

## Overview

DARWIN ZERO-0 is an AI agent framework that starts with **$0 owner-supplied business capital**. All infrastructure, cloud costs, and operational expenses are accounted separately from business capital unless the owner later changes this policy.

## Core Directives (from policies)

1. **Capital**: $0 owner-supplied business capital. Free/local/open-source capabilities preferred.
2. **Constitution**: Human owner retains ultimate control over assets, wallets, permissions, audit logs, rollback, pause, freeze, and termination.
3. **Financial policy**: No debt, interest, leverage, futures, CFDs, short selling, betting, or gambling. Paid upgrades require positive expected economic value.
4. **Bug bounty**: Security research only with active, authorized programs and in-scope targets.
5. **Decision protocol**: Record objective, evidence, assumptions, unknowns, options, upside, downside, confidence, cost, time, opportunity cost, reputation impact, reversibility, policy compatibility, reviewer verdict.
6. **Self-healing**: Detect → capture logs → search incident memory → diagnose → patch candidate → tests → deploy or rollback.
7. **Self-improvement**: Detect gap → gather evidence → compare options → build-vs-buy → isolated sandbox → benchmark → independent review → adopt only if measurably better → monitor → rollback if degrades.
8. **Reproduction**: Child agent requires positive risk-adjusted EV, isolated workspace, separate ledger/budget, separate memory branch, inherited constitution, no access to master wallet keys, supervisor-controlled financial allocation.

## Bootstrap Directory Structure

```
darwin-zero0/
├── README.md                          # Project overview (exists)
├── DARWIN_BOOTSTRAP.md               # This file: system + boot sequence
├── AGENTS.md                         # Repository-wide agent rules
├── policies/                        # Owner-controlled policy (DO NOT WEAKEN)
│   ├── DARWIN_CONSTITUTION.md
│   ├── FINANCIAL_POLICY.md
│   └── BUG_BOUNTY_POLICY.md
├── protocols/                       # Operational protocols (DO NOT WEAKEN)
│   ├── DECISION_PROTOCOL.md
│   ├── SELF_HEALING_PROTOCOL.md
│   ├── SELF_IMPROVEMENT_PROTOCOL.md
│   └── REPRODUCTION_PROTOCOL.md
├── core/                            # Core runtime
│   ├── __init__.py
│   ├── statemanager.py               # ZERO-0 state (machine-readable schema)
│   └── statemanager_schema.json      # Machine-readable state foundation
├── agents/                          # Agent orchestration
│   ├── __init__.py
│   ├── base_agent.py                 # Base agent class with decision protocol
│   ├── opportunity_agent.py          # Darwin Opportunity Analyst
│   ├── risk_capital_agent.py         # Darwin Risk & Capital Manager
│   └── reviewer_agent.py             # Darwin Reviewer
├── opportunities/                   # Opportunity/evidence tracking
│   ├── __init__.py
│   ├── opportunity.py               # Opportunity model + status tracking
│   └── opportunity_registry.py       # Registry of found opportunities
├── experiments/                     # Experiments
│   ├── __init__.py
│   ├── experiment.py                # Experiment model + lifecycle
│   └── experiment_registry.py        # Registry of running/completed experiments
├── memory/                          # Memory/state
│   ├── __init__.py
│   ├── state.json                     # ZERO-0 persistent state (JSON)
│   └── incident_log.json             # Self-healing incident memory
├── risk/                            # Risk and capital management
│   ├── __init__.py
│   ├── capital_allocator.py          # Capital allocation with EV sizing
│   └── risk_sizer.py                 # Dynamic risk sizing
├── ledger/                          # Accounting/ledger interfaces
│   ├── __init__.py
│   ├── immutable_ledger.py           # Immutable ledger for receipts/expenses
│   └── ledger_schema.json            # Machine-readable ledger schema
├── events/                          # Event bus / event model
│   ├── __init__.py
│   ├── event_model.py                # Core event types and schema
│   └── event_dispatcher.py           # Event dispatch mechanism
├── healing/                         # Self-healing/incidents
│   ├── __init__.py
│   ├── incident.py                   # Incident model
│   ├── incident_handler.py           # Healing loop orchestrator
│   └── incident_knowledge.json       # Reusable fixes knowledge base
├── skills/                          # Skills directory
│   ├── __init__.py
│   └── [skill files created on demand]
├── tools/                           # Tools directory
│   ├── __init__.py
│   └── [tool files created on demand]
├── routing/                         # Model routing
│   ├── __init__.py
│   ├── model_router.py               # Model selection based on task/cost/capability
│   └── router_schema.json            # Model routing schema
├── scouting/                        # Technology scouting
│   ├── __init__.py
│   └── scout.py                      # Capability/gap scanning
├── evolution/                       # Self-improvement/evolution lab
│   ├── __init__.py
│   ├── evolution_lab.py              # Controlled experiments on skills/tools
│   └── benchmark_schema.json         # Benchmark schema for evaluations
├── children/                        # Controlled child-agent lifecycle
│   ├── __init__.py
│   ├── proposal.py                   # Reproduction proposal model
│   └── registry.py                   # Child agent registry
├── tests/                           # Tests
│   ├── __init__.py
│   ├── test_opportunity.py
│   ├── test_experiment.py
│   ├── test_event_model.py
│   └── test_statemanager.py
└── docs/                            # Documentation
    ├── __init__.py
    └── [doc files created on demand]
```

## Boot Sequence

1. **Initialize state**: Load/create `state.json` with ZERO-0 defaults ($0 capital, empty opportunity/experiment heaps, clean incident ledger).
2. **Load policies**: Read DARWIN_CONSTITUTION.md, FINANCIAL_POLICY.md, BUG_BOUNTY_POLICY.md as immutable constraints.
3. **Load protocols**: Read DECISION_PROTOCOL.md, SELF_HEALING_PROTOCOL.md, SELF_IMPROVEMENT_PROTOCOL.md, REPRODUCTION_PROTOCOL.md as operational guides.
4. **Initialize event bus**: Set up event dispatcher with core event types.
5. **Initialize ledger**: Create immutable ledger with opening balance entry ($0).
6. **Register core agents**: Darwin Opportunity Analyst, Darwin Risk & Capital Manager, Darwin Reviewer (can be delegated on demand).
7. **Ready**: System is bootstrapped and ready for opportunity detection and experiment execution.

## Event Model (Machine-Readable)

Core event types with JSON schema:

- **OPPORTUNITY_FOUND**: `{id, timestamp, source, description, evidence, ev, risk, capital_required, status}`
- **EXPERIMENT_STARTED**: `{id, opportunity_id, hypothesis, method, cost, status}`
- **EXPERIMENT_SUCCEEDED**: `{id, opportunity_id, result, learnings, capital_returned}`
- **EXPERIMENT_FAILED**: `{id, opportunity_id, error, lessons, capital_lost}`
- **BUILD_FAILED**: `{id, component, error, retry_count, status}`
- **INCIDENT_DETECTED**: `{id, signature, severity, auto_healable, handler}`
- **CAPABILITY_DISCOVERED**: `{id, name, description, cost, source}`
- **PAYMENT_CONFIRMED**: `{id, source, amount, receipt_id, ledger_entry_id}` (marked carefully — only from trusted sources)
- **CAPITAL_ALLOCATION_PROPOSED**: `{id, ev, risk, capital_requested, reviewer_verdict, final_decision}`
- **REPRODUCTION_PROPOSED**: `{id, funding, scaling, reserve, distribution, child_id, expected_ev, risk_adjusted_ev}`

All events flow through the event bus (events/event_dispatcher.py). Listeners may subscribe for logging, monitoring, or automatic handling (e.g., incident detection → self-healing loop).

## Self-Healing Readiness

The structure is designed so routine failures enter a self-healing loop:

1. **Incident detected** → event dispatched
2. **Handler searches** incident_memory for prior successful fixes
3. **Diagnose** root cause via error signature + context
4. **Patch candidate** created in isolated workspace
5. **Tests** run (regression + health checks)
6. **If successful**: deploy through controlled promotion
7. **If unsuccessful**: rollback and try alternative hypothesis
8. **Save** successful reusable fixes as incident knowledge

## Capital Allocation Logic (High Level)

Capital allocation considers: expected value, maximum loss, liquidity, survival, time, evidence, opportunity cost, reputation, and reversibility. Risk is sized dynamically — high upside does not justify all-in exposure. No debt, interest, leverage, futures, CFDs, short selling, betting, or gambling.

## Notes

- All code is free/open-source/local where possible. No real payments, wallet transactions, purchases, customer outreach, security testing, or autonomous external writes.
- Child agents are isolated economic agents with separate ledger/budget and memory branch.
- Owner controls all financial limits, permissions, audit logs, rollback, pause, freeze, and termination.
- This bootstrap creates the foundational structure only. Skills, tools, and agents are delegated on demand.