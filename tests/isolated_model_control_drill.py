"""Isolated CP13 crash/restart, routing, cache, and Skill drill; no external calls."""

import hashlib
import tempfile
from pathlib import Path

from model_control import (CacheIdentity, CostController, IntegrationCandidate, PromptCache,
                           RouteRequirements, Router, SkillEvaluator, SkillRegistry,
                           TrustedRunBinder, TrustedUsageAttestor, Usage)
from tests.cp13_helpers import budget, digest, models


def main():
    with tempfile.TemporaryDirectory(prefix="cp13-drill-") as temporary:
        root = Path(temporary)
        store = budget(root, 2)
        binder = TrustedRunBinder(b"b" * 32)
        attestor = TrustedUsageAttestor(b"a" * 32)
        binding = binder.bind(store, "run-1", "task-1")
        registry = models()
        route = Router(registry).route(RouteRequirements(
            "coding", frozenset({"coding", "tools"}), context_tokens=100,
            output_tokens=10, privacy_allowed=frozenset({"local"})))
        assert route.estimated_max_micros == 0
        controller = CostController(root / "usage.sqlite3", store, registry, binder, attestor, now=lambda: 1000)
        controller.begin(binding, "free-1", route.model_id, 100, 10)
        controller.mark_dispatched("free-1")
        evidence = attestor.attest("free-1", "local", route.upstream_model, "fixture-call", Usage(90, 8))
        controller.reconcile("free-1", evidence)
        restarted = CostController(root / "usage.sqlite3", store, registry, binder, attestor, now=lambda: 1001)
        assert restarted.status("free-1")["state"] == "RECONCILED" and restarted.verify_ledger()

        paid = restarted.begin(binding, "paid-fixture", "remote.paid.v1", 1000, 100, True)
        assert paid["reserved_micros"] == 1200
        restarted.abort_before_dispatch("paid-fixture")
        assert store.status("run-1")["budgets"]["spend_cents"]["consumed"] == 1

        identity = CacheIdentity(route.model_id, "1" * 64, "2" * 64, "3" * 64,
                                 "task-1", "4" * 64, "cp12-v1", "TRUSTED_DERIVED")
        cache = PromptCache(root / "cache")
        cache.put(identity, "derived context component")
        assert cache.get(identity) == "derived context component"

        code = "def normalize(value):\n    return str(value).strip()\n"
        item = IntegrationCandidate("drill.skill", "skill", "fixture://drill", "commit-1",
                                    digest(code), "fixture", tools_exposed=("normalize",), license_id="MIT")
        skill_registry = SkillRegistry(root / "skills.sqlite3")
        assert skill_registry.register(item) == "CANDIDATE"
        result = SkillEvaluator().evaluate(item, code, True, True, 2, 2,
                                           "d" * 64, "e" * 64, "f" * 64)
        skill_registry.record_evaluation(item.integration_id, result)
        skill_registry.accept(item.integration_id, True, "acceptance://fixture", "c" * 64)
        skill_registry.activate(item.integration_id, item.source_hash)
        assert skill_registry.verify_ledger()
    print("CP13_ISOLATED_MODEL_CONTROL_DRILL=PASS")
    print("PAID_EXTERNAL_CALLS=0")


if __name__ == "__main__":
    main()
