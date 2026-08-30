#!/usr/bin/env python3
"""DARWIN ZERO-0 Capability Registry.

Central registry of what DARWIN can ACTUALLY do, not what it theoretically claims to do.

Statuses: READY, STUB, BROKEN, NEEDS_AUTH, NEEDS_APPROVAL, DISABLED

Each capability record includes: id, name, category, status, description,
evidence, dependencies, required_tools, required_credentials,
owner_approval_required, external_write, financial_risk, security_risk,
last_verified_at, verification_method, notes.

DO NOT label a capability READY unless it has real runtime evidence.
See capability_registry_audit.py for the audit that produced this registry.
"""

from pathlib import Path
import json
from datetime import datetime, timezone


# ── Status constants ──────────────────────────────────────────────────────

STATUS_READY = "READY"
STATUS_STUB = "STUB"
STATUS_BROKEN = "BROKEN"
STATUS_NEEDS_AUTH = "NEEDS_AUTH"
STATUS_NEEDS_APPROVAL = "NEEDS_APPROVAL"
STATUS_DISABLED = "DISABLED"

VALID_STATUSES = {
    STATUS_READY,
    STATUS_STUB,
    STATUS_BROKEN,
    STATUS_NEEDS_AUTH,
    STATUS_NEEDS_APPROVAL,
    STATUS_DISABLED,
}

# ── Registry path ────────────────────────────────────────────────────────

REGISTRY_DIR = Path(__file__).parent
REGISTRY_PATH = REGISTRY_DIR / "capability_registry.json"
REGISTRY_EXAMPLE_PATH = REGISTRY_DIR / "capability_registry.example.json"


# ── Helpers ──────────────────────────────────────────────────────────────

def _now_iso():
    """Return current UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _validate_status(status):
    """Return True if status is a valid status constant."""
    return status in VALID_STATUSES


def _load_registry():
    """Load the capability registry from disk. Returns dict or None."""
    if not REGISTRY_PATH.exists():
        return None
    try:
        with open(REGISTRY_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _save_registry(registry):
    """Persist the capability registry to disk."""
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)


def _ensure_registry():
    """Ensure registry file exists; create from example if missing."""
    if REGISTRY_PATH.exists():
        return _load_registry()
    # Try example file
    if REGISTRY_EXAMPLE_PATH.exists():
        example = _load_registry()  # this will load from example path logic below
        # fallback handled in create_default_registry
    return create_default_registry()


def create_default_registry():
    """Create a default registry from the seed/example template."""
    # Try loading example first
    if REGISTRY_EXAMPLE_PATH.exists():
        registry = _load_from_example(REGISTRY_EXAMPLE_PATH)
        _save_registry(registry)
        return registry

    # Build a minimal default
    registry = {
        "version": "0.1.0",
        "bootstrapped_at": _now_iso(),
        "capabilities": [],
    }
    _save_registry(registry)
    return registry


def _load_from_example(path):
    """Load registry data from an example JSON file."""
    data = json.load(open(path))
    # Ensure structure
    if "capabilities" not in data:
        data["capabilities"] = []
    return data


# ── Core API ─────────────────────────────────────────────────────────────

def register_capability(
    *,
    id: str,
    name: str,
    category: str,
    status: str,
    description: str = "",
    evidence: list = None,
    dependencies: list = None,
    required_tools: list = None,
    required_credentials: list = None,
    owner_approval_required: bool = False,
    external_write: bool = False,
    financial_risk: bool = False,
    security_risk: bool = False,
    last_verified_at: str = None,
    verification_method: str = "",
    notes: str = "",
):
    """Register a new capability in the registry.

    Args:
        id: Unique capability identifier
        name: Human-readable capability name
        category: Category string (e.g., 'runtime', 'model', 'accounting')
        status: One of READY, STUB, BROKEN, NEEDS_AUTH, NEEDS_APPROVAL, DISABLED
        description: Human-readable description
        evidence: List of evidence strings supporting this status claim
        dependencies: List of capability IDs this depends on
        required_tools: List of tool names required
        required_credentials: List of credential names required
        owner_approval_required: Whether owner approval is needed
        external_write: Whether this capability writes externally
        financial_risk: Whether this has financial risk
        security_risk: Whether this has security risk
        last_verified_at: ISO timestamp of last verification
        verification_method: How the capability was verified
        notes: Additional notes

    Raises:
        ValueError: If status is invalid or id/name already exists
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_STATUSES}")

    registry = _load_registry()
    if registry is None:
        registry = create_default_registry()

    # Check for duplicate id
    caps = registry.get("capabilities", [])
    for cap in caps:
        if cap.get("id") == id:
            raise ValueError(f"Capability ID '{id}' already exists")

    # Check for duplicate name (case-insensitive)
    for cap in caps:
        if cap.get("name", "").lower() == name.lower():
            raise ValueError(f"Capability name '{name}' already exists")

    capability = {
        "id": id,
        "name": name,
        "category": category,
        "status": status,
        "description": description,
        "evidence": evidence if evidence is not None else [],
        "dependencies": dependencies if dependencies is not None else [],
        "required_tools": required_tools if required_tools is not None else [],
        "required_credentials": required_credentials if required_credentials is not None else [],
        "owner_approval_required": owner_approval_required,
        "external_write": external_write,
        "financial_risk": financial_risk,
        "security_risk": security_risk,
        "last_verified_at": last_verified_at or _now_iso(),
        "verification_method": verification_method,
        "notes": notes,
    }

    caps.append(capability)
    registry["capabilities"] = caps
    registry["updated_at"] = _now_iso()
    _save_registry(registry)
    return capability


def update_capability_status(id, new_status):
    """Update the status of an existing capability.

    Args:
        id: Capability ID to update
        new_status: New status string

    Raises:
        ValueError: If capability not found or status is invalid
    """
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{new_status}'. Must be one of {VALID_STATUSES}")

    registry = _load_registry()
    if registry is None:
        raise ValueError("Registry not initialized")

    caps = registry.get("capabilities", [])
    found = False
    for cap in caps:
        if cap.get("id") == id:
            cap["status"] = new_status
            cap["last_verified_at"] = _now_iso()
            found = True
            break

    if not found:
        raise ValueError(f"Capability ID '{id}' not found in registry")

    registry["updated_at"] = _now_iso()
    _save_registry(registry)
    return True


def get_capability(id):
    """Retrieve a capability by ID."""
    registry = _load_registry()
    if registry is None:
        return None
    caps = registry.get("capabilities", [])
    for cap in caps:
        if cap.get("id") == id:
            return cap
    return None


def list_capabilities(category=None, status=None):
    """List capabilities, optionally filtered by category or status."""
    registry = _load_registry()
    if registry is None:
        return []
    caps = registry.get("capabilities", [])
    filtered = caps
    if category:
        filtered = [c for c in filtered if c.get("category") == category]
    if status:
        filtered = [c for c in filtered if c.get("status") == status]
    return filtered


def validate_capability(capability):
    """Validate a capability dict has all required fields with correct types.

    Returns (valid, errors_list).
    """
    required_fields = {
        "id": str,
        "name": str,
        "category": str,
        "status": str,
        "description": str,
        "evidence": list,
        "dependencies": list,
        "required_tools": list,
        "required_credentials": list,
        "owner_approval_required": bool,
        "external_write": bool,
        "financial_risk": bool,
        "security_risk": bool,
        "last_verified_at": str,
        "verification_method": str,
        "notes": str,
    }

    errors = []
    for field, expected_type in required_fields.items():
        if field not in capability:
            errors.append(f"Missing required field: {field}")
        elif not isinstance(capability[field], expected_type):
            errors.append(
                f"Field '{field}' expected type {expected_type.__name__}, got {type(capability[field]).__name__}"
            )

    # Validate status is valid
    if "status" in capability and capability["status"] not in VALID_STATUSES:
        errors.append(f"Invalid status: {capability['status']}. Must be one of {VALID_STATUSES}")

    return len(errors) == 0, errors


# ── Pre-registered DARWIN ZERO-0 capabilities (audit-verified) ──────────

# These capabilities have been audited against actual runtime evidence.
# See the audit in capability_registry_audit.py for the detailed assessment.

_AUDITED_CAPABILITIES = [

    # TechnologyScout baseline - available but static, not live autonomous scouting
    {
        "id": "cap_local_python",
        "name": "Local Python Execution",
        "category": "runtime",
        "status": STATUS_STUB,
        "description": "Python 3.11+ runtime with standard library for local computation, analysis, and automation",
        "evidence": [
            "Python 3.11+ is available on the host system (verified at bootstrap)",
            "exec() and subprocess modules functional per test_foundational.py test_risk_sizer",
        ],
        "dependencies": [],
        "required_tools": ["python3"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "system python --version; pytest execution",
        "notes": "STATIC capability: Python runtime is available but this registry entry is STUB, not READY. The TechnologyScout scans baseline capabilities at bootstrap but does NOT perform live autonomous scouting. Per Phase 2 requirement 4: 'static TechnologyScout must not be labeled as live autonomous scouting'.",
    },
    # Local LLM inference via free model
    {
        "id": "cap_local_llm",
        "name": "Local LLM Inference",
        "category": "model",
        "status": STATUS_STUB,
        "description": "Nemotron 3.5 Lightning free model via opencode-free provider for inference requests",
        "evidence": [
            "Model router configured with nemotron-3.5-lightning-free as default (state.json, AGENTS.md)",
            "execute_code calls via Python venv / hermes deps confirm model availability",
            "model_router.route() returns selected_model per test_model_router test",
        ],
        "dependencies": [],
        "required_tools": ["opencode-free", "model_router"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "model_router.route() test; execute_code inference",
        "notes": "STATIC capability: Local LLM inference is configured and functional per test suite, but this is a STUB status. The model router is initialized and works within the $10 cost cap. Per Phase 2 requirement 4: 'static TechnologyScout must not be labeled as live autonomous scouting' — similarly, a configured model router is not 'live autonomous model selection' but a bootstrap tool.",
    },
    # Unit testing framework
    {
        "id": "cap_unit_tests",
        "name": "Unit Testing Framework",
        "category": "testing",
        "status": STATUS_READY,
        "description": "pytest for Python unit tests and integration tests",
        "evidence": [
            "All 14 foundational tests pass (test_foundational.py :: 14 passed)",
            "13 .mjs test files successfully converted from node:test to vitest import syntax",
            "vitest-mjs-test-runner fix verified: all test suites discovered and executed by Vitest",
        ],
        "dependencies": [],
        "required_tools": ["pytest", "vitest"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "pytest run-all-tests; vitest test execution",
        "notes": "READY: Unit testing framework is fully operational. All 14 foundational tests pass, 13 .mjs test files converted to vitest, and vitest discovery is functional.",
    },
    # Immutable append-only ledger
    {
        "id": "cap_immutable_ledger",
        "name": "Immutable Append-Only Ledger",
        "category": "accounting",
        "status": STATUS_STUB,
        "description": "Append-only financial ledger with JSON state management; entries never mutated, only appended",
        "evidence": [
            "ImmutableLedger class exists in ledger/immutable_ledger.py",
            "Ledger records opening_balance (0c), expense (100c), revenue (200c) per state.json",
            "ledger.get_ledger_summary() returns total_in/out/net cents per test_ledger test",
            "Per FINANCIAL_POLICY.md: 'LLM estimates are NOT financial truth' — ledger records trusted sources only",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py", "core/state.json"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "ImmutableLedger tests; ledger.get_ledger_summary()",
        "notes": "STATIC capability: The ledger is append-only per design. It is STUB, not READY, because it must NOT be labeled 'cryptographically immutable' per Phase 2 requirement 4: 'append-only ledger must not be labeled cryptographically immutable'. The ledger is JSON-based, append-only, owner-controlled — not cryptographically secured.",
    },
    # Event bus / event model
    {
        "id": "cap_event_bus",
        "name": "Event Bus / Event Model",
        "category": "infrastructure",
        "status": STATUS_READY,
        "description": "Dispatch mechanism for major system events (OPPORTUNITY_FOUND, EXPERIMENT_STARTED, etc.)",
        "evidence": [
            "EventDispatcher class in events/event_model.py with all event type methods",
            "13 events dispatched and logged in state.json during bootstrap (OPPORTUNITY_FOUND, CAPITAL_ALLOCATION_PROPOSED, REPRODUCTION_PROPOSED)",
            "test_event_dispatcher, test_opportunity_creation, test_experiment_creation all pass",
            "Convenience methods: opportunity_found, experiment_started, experiment_succeeded, experiment_failed, build_failed, incident_detected, capability_discovered, payment_confirmed, capital_allocation_proposed, reproduction_proposed",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "test_event_dispatcher; test_opportunity_creation; test_experiment_creation; full foundational test suite",
        "notes": "READY: Event bus is fully operational. All event types dispatch and append to state. The foundational test suite (14/14 passed) validates event dispatching.",
    },
    # Self-healing loop (scaffolding, not full E2E)
    {
        "id": "cap_self_healing",
        "name": "Self-Healing Loop",
        "category": "automation",
        "status": STATUS_STUB,
        "description": "11-step protocol for detecting and resolving routine failures",
        "evidence": [
            "healing/ directory exists but is empty (no healing implementations yet)",
            "INCIDENT_DETECTED event type defined in events/event_model.py",
            "INCIDENT_DETECTED can be dispatched per event_model tests",
            "Per SELF_IMPROVEMENT_PROTOCOL.md: 11-step protocol framework exists but no E2E implementations adopted yet",
        ],
        "dependencies": [],
        "required_tools": ["events/event_model.py", "core/statemanager.py"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "INCIDENT_DETECTED event dispatch; healing/ directory scan",
        "notes": "STATIC capability: Self-healing scaffolding exists as protocol framework but is STUB, not READY. Per Phase 2 requirement 4: 'self-healing scaffolding must not be labeled full E2E self-healing'. The 11-step protocol is defined in SELF_IMPROVEMENT_PROTOCOL.md but no full end-to-end healing loop has been adopted. Healing/ directory is empty at bootstrap.",
    },
    # Model Router
    {
        "id": "cap_model_router",
        "name": "Model Router",
        "category": "infrastructure",
        "status": STATUS_STUB,
        "description": "Routes tasks to appropriate models based on cost, latency, and capability",
        "evidence": [
            "ModelRouter class in routing/model_router.py with DEFAULT_CONFIG",
            "test_model_router passes: router.route() returns selected_model and cost_sensitive",
            "model_router.route(classification, cost_sensitivity=True, latency_requirement='normal') works per foundational test",
            "Free model preference per FINANCIAL_POLICY.md: nemotron-3.5-lightning-free default",
            "Cost cap of $10 (1000 cents) enforced per config",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "test_model_router; model_router.route() calls",
        "notes": "STATIC capability: Model Router is functional and tested but marked STUB, not READY. Per Phase 2 requirement 4: model router configuration is not 'live autonomous model selection'. It is a bootstrap tool with free model preference and $10 cost cap. The router makes deterministic selections based on task type and cost sensitivity — not autonomous model selection in the live sense.",
    },
    # TechnologyScout baseline scan
    {
        "id": "cap_technology_scout",
        "name": "TechnologyScout Baseline Scan",
        "category": "scouting",
        "status": STATUS_STUB,
        "description": "Scans for and evaluates capabilities, tools, models, and services against DARWIN ZERO-0 requirements",
        "evidence": [
            "TechnologyScout class in scouting/scout.py with _baseline_capabilities() returning 8 baseline capabilities",
            "test_technology_scout passes: scout.scan_capabilities() returns baseline caps with cost_cents=0",
            "Baseline capabilities: Local Python, Local LLM, Unit Tests, Immutable Ledger, Event Bus, Self-Healing, Model Router (all listed in scout _baseline_capabilities())",
            "Per SELF_IMPROVEMENT_PROTOCOL.md: capability detection, gap analysis, sandbox trial framework exists",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py", "events/event_model.py"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "test_technology_scout; scout._baseline_capabilities() output",
        "notes": "STATIC capability: TechnologyScout baseline scan is STUB, not READY. Per Phase 2 requirement 4: 'static TechnologyScout must not be labeled as live autonomous scouting'. The scout returns hardcoded baseline capabilities at bootstrap — it does NOT perform live autonomous scouting of PyPI, GitHub, or external services. It is a static registry of what was available at bootstrap time.",
    },
    # Capital allocation
    {
        "id": "cap_capital_allocation",
        "name": "Capital Allocation",
        "category": "financial",
        "status": STATUS_STUB,
        "description": "Dynamic capital allocation considering EV, risk, and policy constraints per FINANCIAL_POLICY.md",
        "evidence": [
            "CapitalAllocator class in risk/capital_allocator.py with allocate() method",
            "test_capital_allocator passes: allocator.allocate() returns decision, allocated_cents",
            "RiskSizer class in risk/risk_sizer.py with size_risk() method",
            "test_risk_sizer passes: sizer.size_risk() returns risk_percent and risk_cents",
            "allocate_for_opportunity() convenience function available",
            "Policy constraints enforced: no debt/leverage/futures/short selling/gambling",
            "Paid upgrades require positive expected economic value vs free/build alternatives",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py", "events/event_model.py"],
        "required_credentials": [],
        "owner_approval_required": True,
        "external_write": False,
        "financial_risk": True,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "test_capital_allocator; test_risk_sizer; allocate_for_opportunity() calls",
        "notes": "STATIC capability: Capital allocation framework is functional and tested but marked STUB, not READY. The allocator and risk sizer work within the $0 owner-supplied capital constraint. Per AGENTS.md: 'ZERO-0 starts with $0 owner-supplied business capital'. Capital allocation is policy-constrained and verified via tests, but not 'live autonomous capital deployment'.",
    },
    # Opportunity model
    {
        "id": "cap_opportunity_model",
        "name": "Opportunity Model",
        "category": "decision",
        "status": STATUS_READY,
        "description": "Models a found opportunity discovered by the Opportunity Analyst; tracks EV, risk, capital required through decision protocol lifecycle",
        "evidence": [
            "Opportunity class in opportunities/opportunity.py with __init__(description, ev_cents, risk, capital_required_cents)",
            "test_opportunity_creation passes: opp.id, opp.status == 'discovered', opp.ev_cents",
            "Opportunities tracked through event bus (OPPORTUNITY_FOUND event dispatched)",
            "Decision protocol lifecycle: discovered → evaluation → allocation → decision",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py", "events/event_model.py"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": True,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "test_opportunity_creation; foundational test suite",
        "notes": "READY: Opportunity model is fully operational. All foundational tests pass. Opportunity creation, status tracking, and event dispatch are verified.",
    },
    # Experiment model
    {
        "id": "cap_experiment_model",
        "name": "Experiment Model",
        "category": "decision",
        "status": STATUS_READY,
        "description": "Models an experiment triggered by an opportunity; has lifecycle and produces learnings that feed back into the opportunity/decision pipeline",
        "evidence": [
            "Experiment class in experiments/experiment.py with __init__(opportunity_id, hypothesis, method, cost_cents)",
            "test_experiment_creation passes: exp.id, exp.status == 'pending'",
            "Experiments linked to opportunities via opportunity_id",
            "Experiment lifecycle: pending → running → succeeded/failed with learnings",
            "Experiment events: EXPERIMENT_STARTED, EXPERIMENT_SUCCEEDED, EXPERIMENT_FAILED",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py", "events/event_model.py"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": True,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "test_experiment_creation; foundational test suite",
        "notes": "READY: Experiment model is fully operational. All foundational tests pass. Experiment creation, status tracking, and event dispatch are verified.",
    },
    # Risk sizing
    {
        "id": "cap_risk_sizing",
        "name": "Risk Sizing",
        "category": "financial",
        "status": STATUS_READY,
        "description": "Dynamic risk sizing per DARWIN ZERO-0 Financial Policy; higher risk_score → more conservative sizing, not greater allocation",
        "evidence": [
            "RiskSizer class in risk/risk_sizer.py with size_risk() and can_risk() methods",
            "test_risk_sizer passes: sizer.size_risk(risk_score=30, ev_cents=500, allocatable_cents=1000)",
            "Policy: higher risk_score → MORE conservative sizing (inverted relationship)",
            "Negative EV → risk_cents=0 per policy",
            "Survival floor: always keep at least SURVIVAL_FLOOR_CENTS=100 in reserve",
            "High risk (>=80) capped at MIN_ALLOCATABLE_FRACTION=1% of allocatable",
            "All 14 foundational tests pass including risk sizing tests",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": True,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "test_risk_sizer; size_risk() and can_risk() calls; full foundational test suite",
        "notes": "READY: Risk sizing is fully operational with verified policy constraints. The inverted risk_score→conservative_sizing relationship is implemented and tested. All foundational tests pass.",
    },
    # Ledger (immutable append-only)
    {
        "id": "cap_ledger_operations",
        "name": "Ledger Operations",
        "category": "accounting",
        "status": STATUS_STUB,
        "description": "Append-only ledger operations: record_expense, record_revenue, record_capital_allocation, get_ledger_summary",
        "evidence": [
            "ImmutableLedger class in ledger/immutable_ledger.py",
            "test_ledger passes: record_expense(100, 'Test expense'), record_revenue(200, 'Test revenue')",
            "Ledger summary: total_in_cents, total_out_cents, net_cents, entry_count all return",
            "Opening balance: $0 owner-supplied business capital per AGENTS.md",
            "Per FINANCIAL_POLICY.md: 'LLM estimates are NOT financial truth' — only trusted sources confirm balances",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py", "core/state.json"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "test_ledger; ImmutableLedger methods; ledger.get_ledger_summary()",
        "notes": "STATIC capability: Ledger operations are STUB, not READY. Per Phase 2 requirement 4: 'append-only ledger must not be labeled cryptographically immutable'. The ledger is JSON-based, append-only, owner-controlled — not cryptographically secured. Operations work but the status reflects the limited cryptographic guarantee.",
    },
    # Evolution Lab (self-improvement)
    {
        "id": "cap_evolution_lab",
        "name": "Evolution Lab / Self-Improvement",
        "category": "automation",
        "status": STATUS_STUB,
        "description": "Controlled self-improvement/evolution lab for isolated sandbox trials of skills, prompts, tools, services, models, workflows, and code",
        "evidence": [
            "EvolutionLab class in evolution/evolution_lab.py with detect_gap, gather_evidence, compare_options, run_sandbox_trial, independent_review, monitor_impact, rollback_or_retire methods",
            "Per SELF_IMPROVEMENT_PROTOCOL.md: 11-step framework for capability improvement",
            "All evolution lab methods functional per code review",
            "Sandbox trials are isolated; no external modifications without review adoption",
            "Independent review and rollback/retire capabilities implemented",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py", "experiments/experiment.py", "events/event_model.py"],
        "required_credentials": [],
        "owner_approval_required": True,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "EvolutionLab method calls; SELF_IMPROVEMENT_PROTOCOL.md compliance",
        "notes": "STATIC capability: Evolution Lab framework is STUB, not READY. The 11-step self-improvement protocol exists but no adopted improvements have been rolled through the full adopt-monitor-rollback cycle. Sandbox trials are isolated per protocol. No production improvements have been adopted yet.",
    },
    # Child/Reproduction Proposals
    {
        "id": "cap_child_proposals",
        "name": "Child/Reproduction Proposals",
        "category": "reproduction",
        "status": STATUS_STUB,
        "description": "Controlled child agent lifecycle per REPRODUCTION_PROTOCOL.md; positive risk-adjusted EV required; no access to master wallet private keys",
        "evidence": [
            "ChildAgentProposal class in children/registry.py with __init__(funding_cents, scaling_reserve_cents, distribution_cents, expected_ev_cents, risk_adjusted_ev_cents)",
            "test_child_proposal passes: proposal with risk_adjusted_ev_cents=800, status != 'rejected'",
            "test_child_negative_ev passes: proposal with risk_adjusted_ev_cents=-100, status == 'rejected'",
            "propose_child() convenience function dispatches REPRODUCTION_PROPOSED event",
            "Per REPRODUCTION_PROTOCOL.md: child requires positive risk-adjusted EV, isolated workspace, separate ledger/budget, separate memory branch, no access to master wallet private keys (key_access=False)",
            "Children/registry.py StateManager loads/saves state.json children array",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py", "events/event_model.py"],
        "required_credentials": [],
        "owner_approval_required": True,
        "external_write": False,
        "financial_risk": True,
        "security_risk": True,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "test_child_proposal; test_child_negative_ev; propose_child() event dispatch; children array in state.json",
        "notes": "STATIC capability: Child proposal support is STUB, not READY. Per Phase 2 requirement 4: 'reproduction proposal support must not be labeled autonomous child isolation'. The system supports proposals with positive risk-adjusted EV and validated rejections of negative-EV proposals, but no child agents have been created with full isolated workspace, separate ledger/budget, and separate memory branch. key_access=False enforced per protocol.",
    },
    # Hermes delegation (integrated in statemanager, not separate module)
    {
        "id": "cap_hermes_delegation",
        "name": "Hermes Delegation",
        "category": "infrastructure",
        "status": STATUS_STUB,
        "description": "Agent delegation via Hermes event bus and state management; supervisor/owner-controlled financial allocation",
        "evidence": [
            "State manager provides init_state, load_state, append_event, append_ledger_entry, append_opportunity, append_experiment, append_capability, append_child functions",
            "Children/registry.py integrates with state manager for proposal recording",
            "Event dispatcher provides capability_discovered, reproduction_proposed, capital_allocation_proposed event methods",
            "Per AGENTS.md: core agents dormant until triggered; skills and tools loaded on demand via Hermes",
            "No permanently active specialist agents; child agents isolated with separate ledger/budget/memory branch",
        ],
        "dependencies": [],
        "required_tools": ["core/statemanager.py", "events/event_model.py"],
        "required_credentials": [],
        "owner_approval_required": True,
        "external_write": False,
        "financial_risk": True,
        "security_risk": True,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "statemanager functions; children registry integration; event dispatcher methods; AGENTS.md compliance",
        "notes": "STATIC capability: Hermes delegation is STUB, not READY. The infrastructure exists (state manager, event dispatcher, children registry) but no live autonomous delegation is active. Core agents are dormant per AGENTS.md; skills/tools loaded on demand. Child agents require supervisor/owner-controlled financial allocation and have no access to master wallet private keys.",
    },
    # Terminal/code execution
    {
        "id": "cap_terminal_execution",
        "name": "Terminal / Code Execution",
        "category": "runtime",
        "status": STATUS_READY,
        "description": "Python code execution via execute_code tool; persistent kernel with surviving state across calls; hermes_tools execute_code sandbox",
        "evidence": [
            "execute_code tool runs Python in persistent session kernel",
            "Variables, imports, and loaded data survive across execute_code calls",
            "13 .mjs test files successfully converted and executed by Vitest via execute_code",
            "from hermes_tools import ... imports work persistently",
            "terminal() calls persist state between invocations",
        ],
        "dependencies": [],
        "required_tools": ["hermes_tools execute_code", "python 3.11+"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": False,
        "financial_risk": False,
        "security_risk": False,
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "execute_code tool calls; persistent kernel state survival; Vitest .mjs test execution",
        "notes": "READY: Terminal/code execution is fully operational. The execute_code tool runs Python in a persistent kernel where variables, imports, and loaded data survive across calls. 13 .mjs test files converted from node:test to vitest import syntax and successfully executed by Vitest via this mechanism.",
    },
    # Browser/web capability (available via Browser Use CLI)
    {
        "id": "cap_browser_web",
        "name": "Browser / Web Capability",
        "category": "web",
        "status": STATUS_STUB,
        "description": "Browser Use CLI for web interaction; can navigate, extract, click, capture screenshots via CDP",
        "evidence": [
            "browser_exec tool available: drives real web browser via Browser Use CLI",
            "code runs as full Python with pre-imported browser helpers",
            "session persists across calls; workspace dir $BH_AGENT_WORKSPACE",
            "Helpers: new_tab, goto_url, wait_for_load, page_info, js, fill_input, click_at_xy, capture_screenshot",
            "cdp('Accessibility.getFullAXTree'), cdp('DOM.getBoxModel') available",
            "Per Phase 2: browser/web capability is available but STUB — not live autonomous web agent",
        ],
        "dependencies": [],
        "required_tools": ["browser_exec (Browser Use CLI)", "Python 3.11+"],
        "required_credentials": [],
        "owner_approval_required": False,
        "external_write": True,  # Can write to web pages, save files, navigate external URLs
        "financial_risk": False,
        "security_risk": True,  # Web navigation has security considerations
        "last_verified_at": "2026-08-30T20:30:10.887640+00:00",
        "verification_method": "browser_exec tool invocation; js() evaluations; capture_screenshot output",
        "notes": "STATIC capability: Browser/web capability is STUB, not READY. Per Phase 2 requirement: the Browser Use CLI is available and functional for text-first DOM extraction and extraction, but this is not a 'live autonomous web agent'. It is a tool-assisted browser capability for capability discovery and web content extraction. No autonomous web browsing or navigation is claimed.",
    },
]

# ── Module-level init ────────────────────────────────────────────────────

def init_registry():
    """Initialize the capability registry with audited capabilities.

    Should be called once at bootstrap. Idempotent: if registry already exists
    with valid structure, does nothing.
    """
    registry = _load_registry()
    if registry is not None:
        # Verify it has capabilities list
        if "capabilities" in registry and len(registry["capabilities"]) > 0:
            return registry  # Already initialized

    # Create default with audited capabilities
    registry = {"version": "0.1.0", "bootstrapped_at": _now_iso(), "capabilities": []}
    for cap in _AUDITED_CAPABILITIES:
        caps = registry.setdefault("capabilities", [])
        # Validate each capability before adding
        valid, errors = validate_capability(cap)
        if not valid:
            print(f"WARNING: Capability {cap.get('id', 'unknown')} failed validation: {errors}")
            continue
        caps.append(cap)

    registry["updated_at"] = _now_iso()
    _save_registry(registry)
    return registry


# ── Convenience functions ────────────────────────────────────────────────

def list_ready():
    """Return all capabilities with status READY."""
    registry = _load_registry()
    if registry is None:
        return []
    return [c for c in registry.get("capabilities", []) if c.get("status") == STATUS_READY]


def list_stub():
    """Return all capabilities with status STUB."""
    registry = _load_registry()
    if registry is None:
        return []
    return [c for c in registry.get("capabilities", []) if c.get("status") == STATUS_STUB]


def list_broken():
    """Return all capabilities with status BROKEN."""
    registry = _load_registry()
    if registry is None:
        return []
    return [c for c in registry.get("capabilities", []) if c.get("status") == STATUS_BROKEN]


def list_needs_auth():
    """Return all capabilities with status NEEDS_AUTH."""
    registry = _load_registry()
    if registry is None:
        return []
    return [c for c in registry.get("capabilities", []) if c.get("status") == STATUS_NEEDS_AUTH]


def list_needs_approval():
    """Return all capabilities with status NEEDS_APPROVAL."""
    registry = _load_registry()
    if registry is None:
        return []
    return [c for c in registry.get("capabilities", []) if c.get("status") == STATUS_NEEDS_APPROVAL]


def list_disabled():
    """Return all capabilities with status DISABLED."""
    registry = _load_registry()
    if registry is None:
        return []
    return [c for c in registry.get("capabilities", []) if c.get("status") == STATUS_DISABLED]


# ── Bootstrap ────────────────────────────────────────────────────────────

# Initialize registry when module is imported
_registry = init_registry()

if __name__ == "__main__":
    # Simple CLI: show registry status
    import json, sys
    registry = _load_registry()
    if registry is None:
        print("Registry not initialized. Run init_registry().")
        sys.exit(1)
    print(json.dumps(registry, indent=2))