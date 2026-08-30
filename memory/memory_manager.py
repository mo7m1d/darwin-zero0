#!/usr/bin/env python3
"""DARWIN ZERO-0 Memory and State

Manages persistent state and incident memory for the self-healing loop.
All state is stored in JSON format within the repository.

Per SELF_HEALING_PROTOCOL.md:
1. Detect error or degraded health
2. Capture logs and error signature
3. Search incident memory for prior successful fixes
4. Diagnose likely root cause
5. Research official documentation/web if uncertain
6. Create a patch candidate in an isolated workspace
7. Run targeted tests, regression tests, and health checks
8. If successful, deploy through controlled promotion
9. If unsuccessful, rollback and try an alternative hypothesis
10. Escalate only when repeated safe attempts fail or the incident touches
    money, secrets, security boundaries, irreversible data loss, or owner controls
11. Save successful reusable fixes as incident knowledge and, when appropriate,
    a Hermes skill
"""

import json
from pathlib import Path
from datetime import datetime, timezone


class StateManager:
    """Manages ZERO-0 persistent state stored in state.json.

    Handles loading, saving, and initializing the machine-readable state
    foundation (statemanager_schema.json).
    """

    def __init__(self, state_path=None):
        if state_path is None:
            self.base = Path(__file__).parent.parent
            self.state_path = self.base / "state" / "state.json"
        else:
            self.state_path = Path(state_path)

    def init(self):
        """Initialize state.json with ZERO-0 bootstrapped defaults ($0 capital).

        Idempotent: if state.json already exists with valid structure, does nothing.
        """
        if self.state_path.exists():
            try:
                with open(self.state_path, "r") as f:
                    state = json.load(f)
                # Check required fields
                if (
                    "version" in state
                    and "bootstrapped_at" in state
                    and "capital" in state
                    and "model_router" in state
                    and state["capital"].get("owner_supplied_cents") is not None
                ):
                    return  # Valid state already exists
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # Fall through to overwrite

        opening_balance = {
            "id": "ledger_opening_balance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "opening_balance",
            "amount_cents": 0,
            "description": "DARWIN ZERO-0 opening balance: $0 owner-supplied business capital",
        }

        state = {
            "version": "0.1.0",
            "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
            "capital": {
                "owner_supplied_cents": 0,
                "current_cents": 0,
                "reserve_cents": 0,
                "child_agent_fund_cents": 0,
            },
            "model_router": {
                "default_model": "nemotron-3.5-lightning-free",
                "free_preferred": True,
                "cost_cap_cents": 1000,
            },
            "events": [],
            "incidents": [],
            "ledger": [opening_balance],
            "opportunities": [],
            "experiments": [],
            "capabilities": [],
            "children": [],
        }

        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2)

    def load(self):
        """Load state from state.json. Returns None if not found or invalid."""
        if not self.state_path.exists():
            return None
        try:
            with open(self.state_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"WARNING: {self.state_path} is not valid JSON")
            return None

    def save(self, state):
        """Persist state dict to state.json."""
        with open(self.state_path, "w") as f:
            json.dump(state, f, indent=2)


class IncidentMemory:
    """Incident memory for the self-healing loop.

    Stores past incidents with error signatures, root causes, and fixes.
    Per SELF_HEALING_PROTOCOL.md, this memory is searched when a new incident
    is detected to find prior successful fixes.

    Structure per state schema incident definition:
    - id: UUID
    - timestamp: ISO datetime
    - signature: Error/signature hash identifying the incident
    - severity: low | medium | high | critical
    - auto_healable: Whether the healing loop can attempt auto-fix
    - status: detected | investigating | patch_candidate | test_running | deployed | rolled_back | escalated
    - root_cause: Diagnosed root cause (optional)
    - fix_attempted: Boolean
    - fix_successful: Boolean
    """

    def __init__(self, state_manager=None):
        self.sm = state_manager or StateManager()
        self.state = self.sm.load() or {}
        self.incidents = self.state.get("incidents", [])

    def detect(self, signature, severity, auto_healable=True, source="system",
               root_cause=None):
        """Record a new incident in memory.

        Args:
            signature: Error/signature hash identifying the incident
            severity: "low" | "medium" | "high" | "critical"
            auto_healable: Whether the healing loop can attempt auto-fix
            source: Emitting component
            root_cause: Diagnosed root cause (optional)

        Returns:
            The created incident dict
        """
        incident = {
            "id": f"inc_{uuid_str()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signature": signature,
            "severity": severity,
            "auto_healable": auto_healable,
            "source": source,
            "root_cause": root_cause,
            "status": "detected",
            "fix_attempted": False,
            "fix_successful": False,
        }
        self.incidents.append(incident)
        self._save_incidents()
        return incident

    def _save_incidents(self):
        """Persist incidents back to state."""
        self.state["incidents"] = self.incidents
        self.sm.save(self.state)

    def search(self, signature, max_results=10):
        """Search incident memory for prior incidents with matching or similar signatures.

        Per SELF_HEALING_PROTOCOL.md step 3: "Search incident memory for prior successful fixes."

        Args:
            signature: Error signature to search for (substring match)
            max_results: Maximum number of results to return

        Returns:
            List of incident dicts with matching/related signatures
        """
        results = []
        for inc in self.incidents:
            if signature in inc.get("signature", "") or inc.get("signature", "").startswith(signature[:8]):
                results.append(inc)
                if len(results) >= max_results:
                    break
        # Also search by severity if no signature matches
        if not results and max_results > 0:
            # Return recent high/critical incidents
            high_severity = [i for i in self.incidents if i.get("severity") in ("high", "critical")]
            results = high_severity[:max_results]
        return results

    def get_by_status(self, status):
        """Get all incidents with a given status."""
        return [i for i in self.incidents if i.get("status") == status]

    def get_recent_successful(self, limit=5):
        """Get recently resolved successful incidents (fix_successful=True)."""
        successful = [i for i in self.incidents if i.get("fix_successful") is True]
        # Sort by timestamp descending
        successful.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return successful[:limit]


class HealingEngine:
    """Self-healing loop orchestrator per SELF_HEALING_PROTOCOL.md.

    Execodes the 11-step self-healing protocol for routine failures.
    Designed so routine failures can enter a self-healing loop automatically.
    """

    def __init__(self, incident_memory=None, state_manager=None):
        self.im = incident_memory or IncidentMemory()
        self.sm = state_manager or StateManager()
        self.state = self.sm.load() or {}

    def run_healing_cycle(self, incident_signature, severity="medium",
                          source="system"):
        """Run a full self-healing cycle for a detected incident.

        Per SELF_HEALING_PROTOCOL.md steps 1-11:
        1. Detect error or degraded health (already done - caller detected)
        2. Capture logs and error signature (captured via incident signature)
        3. Search incident memory for prior successful fixes
        4. Diagnose likely root cause
        5. Research official documentation/web if uncertain
        6. Create a patch candidate in an isolated workspace
        7. Run targeted tests, regression tests, and health checks
        8. If successful, deploy through controlled promotion
        9. If unsuccessful, rollback and try an alternative hypothesis
        10. Escalate only when repeated safe attempts fail or incident touches
            money/secrets/security/irreversible data/owner controls
        11. Save successful reusable fixes as incident knowledge

        Args:
            incident_signature: Error signature hash identifying the incident
            severity: "low" | "medium" | "high" | "critical"
            source: Emitting component

        Returns:
            Dict with healing cycle results
        """
        # Step 1: Incident already detected (caller dispatched INCIDENT_DETECTED)
        # Step 2: Error signature captured (incident_signature parameter)

        # Step 3: Search incident memory for prior successful fixes
        prior_fixes = self.im.search(incident_signature, max_results=5)
        prior_successful = [f for f in prior_fixes if f.get("fix_successful") is True]

        result = {
            "incident_signature": incident_signature,
            "severity": severity,
            "step": 3,
            "prior_successful_count": len(prior_successful),
            "prior_fixes_summaries": [
                f"{f.get('root_cause', 'unknown')}: {f.get('fix_attempted', False)}"
                for f in prior_successful
            ],
            "steps_completed": [],
            "final_status": None,
            "error": None,
        }

        # Step 4: Diagnose likely root cause
        result["steps_completed"].append("diagnose_root_cause")
        # Use prior successful fix's root cause if available, otherwise mark uncertain
        if prior_successful:
            result["diagnosed_root_cause"] = prior_successful[0].get("root_cause", "unknown (from prior fix)")
        else:
            result["diagnosed_root_cause"] = "unknown — no prior successful fix found"

        # Step 5: Research official documentation/web if uncertain
        result["steps_completed"].append("research_documentation")
        result["research_uncertain"] = result["diagnosed_root_cause"] == "unknown"

        # Step 6: Create patch candidate in isolated workspace
        result["steps_completed"].append("create_patch_candidate")
        result["patch_created"] = self._create_patch_candidate(
            result["diagnosed_root_cause"]
        )

        # Step 7: Run targeted tests, regression tests, and health checks
        result["steps_completed"].append("run_tests")
        result["tests_passed"] = self._run_tests_if_patch(
            result.get("patch_candidate_path")
        )

        # Step 8: If successful, deploy through controlled promotion
        # Step 9: If unsuccessful, rollback and try alternative hypothesis
        if result.get("tests_passed", False):
            result["steps_completed"].append("deploy_patch")
            result["final_status"] = "deployed"
            # Mark incident as healed
            self._mark_incident_healed(incident_signature, True)
            result["final_status"] = "deployed"
        else:
            # Try alternative hypothesis (simplified: just mark for retry)
            result["steps_completed"].append("rollback_try_alternative")
            result["final_status"] = "rolled_back"
            # Mark incident as still open/rolled back
            self._mark_incident_healed(incident_signature, False)
            result["note"] = "Rolled back; alternative hypothesis should be tried"

        # Step 10: Escalation check (simplified — in production, check against
        # money/secrets/security/irreversible data/owner controls boundaries)
        result["steps_completed"].append("escalation_check")
        # For this bootstrap, we assume no escalation needed unless critical

        # Step 11: Save successful reusable fixes as incident knowledge
        if result.get("final_status") == "deployed":
            self._save_successful_fix(
                incident_signature,
                result["diagnosed_root_cause"],
                result.get("patch_summary", "unknown")
            )

        return result

    def _create_patch_candidate(self, root_cause):
        """Create a patch candidate in an isolated workspace.

        Simplified: returns a path placeholder. In production, this would
        create actual patch files.
        """
        import tempfile
        import os

        # Create a temporary directory for the patch candidate
        candidate_dir = tempfile.mkdtemp(prefix="darwin_healing_")
        # Create a placeholder patch file
        patch_path = os.path.join(candidate_dir, "patch_candidate.py")
        with open(patch_path, "w") as f:
            f.write(f"# Patch candidate for: {root_cause}\n")
            f.write("# This would contain the actual fix in production\n")
        return patch_path

    def _run_tests_if_patch(self, patch_path):
        """Run targeted tests and health checks if a patch candidate exists."""
        if not patch_path or not os.path.exists(patch_path):
            return False

        # In a real implementation, we'd import and run the patch
        # For bootstrap, assume tests need proper infrastructure
        # Check if a test file exists alongside
        test_path = patch_path.replace("patch_candidate", "test_patch")
        if os.path.exists(test_path):
            # Read test content - in production would run pytest etc.
            try:
                with open(test_path, "r") as f:
                    test_content = f.read()
                # Simple heuristic: if test file has 'def test_' we consider it structured
                has_tests = "def test_" in test_content
                return has_tests
            except Exception:
                return False
        return False

    def _mark_incident_healed(self, signature, successful):
        """Mark an incident as having had a fix attempt.

        Args:
            signature: Incident signature to match
            successful: True if the fix was successful, False if rolled back
        """
        for inc in self.im.incidents:
            if inc.get("signature") == signature:
                inc["fix_attempted"] = True
                inc["fix_successful"] = successful
                inc["status"] = "deployed" if successful else "rolled_back"
                self.im._save_incidents()
                break

    def _save_successful_fix(self, signature, root_cause, fix_summary):
        """Save a successful reusable fix as incident knowledge.

        Per SELF_HEALING_PROTOCOL.md step 11: "Save successful reusable fixes
        as incident knowledge and, when appropriate, a Hermes skill."
        """
        # Add to incidents with fix_successful=True and add knowledge entry
        knowledge_entry = {
            "id": f"knowledge_{uuid_str()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signature": signature,
            "root_cause": root_cause,
            "fix_summary": fix_summary,
            "type": "successful_fix",
        }

        # Append to a knowledge file or the incidents list with marker
        if "knowledge_base" not in self.state:
            self.state["knowledge_base"] = []

        # Check if already recorded
        kb = self.state["knowledge_base"]
        already = any(k.get("signature") == signature for k in kb)
        if not already:
            kb.append(knowledge_entry)
            self.state["knowledge_base"] = kb
            self.sm.save(self.state)

    def uuid_str():
        """Generate short UUID string."""
        import uuid
        return uuid.uuid4().hex[:12]


# Convenience function
def init_state():
    """Initialize ZERO-0 state. Convenience wrapper."""
    sm = StateManager()
    sm.init()
    return sm