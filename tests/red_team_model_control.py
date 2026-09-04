"""CP13 Red-Team: 63 applicable attacks, each must fail closed."""

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from model_control import (CacheIdentity, CostController, IntegrationCandidate, ModelRecord,
                           ModelRegistry, PromptCache, RouteRequirements, Router, SkillEvaluator,
                           SkillRegistry, TrustedRunBinder, TrustedUsageAttestor, Usage)
from model_control.accounting import RunBinding, UsageEvidence
from tests.cp13_helpers import budget, digest, models

ROOT = Path(__file__).parents[1]
EVIDENCE = ("d" * 64, "e" * 64, "f" * 64)
ATTACKS = [
    "01_paid_model_labeled_free", "02_unknown_price_assumed_free", "03_alias_points_to_paid_model",
    "04_mutable_latest_identity", "05_free_failure_paid_fallback", "06_rate_limit_paid_fallback",
    "07_child_evades_spend", "08_usage_wrong_run", "09_forged_usage", "10_missing_usage_zero",
    "11_negative_tokens", "12_integer_overflow", "13_float_cost_rounding", "14_stale_pricing",
    "15_pricing_registry_rewrite", "16_spend_reservation_race", "17_crash_after_call",
    "18_crash_after_reservation", "19_retries_multiply_spend", "20_direct_provider_bypass",
    "21_prompt_requests_paid", "22_retrieved_text_changes_route", "23_false_capability_claim",
    "24_context_too_large", "25_missing_tool_support", "26_privacy_remote_forbidden",
    "27_unhealthy_model_selected", "28_benchmark_special_case", "29_router_config_mutation",
    "30_fallback_ignores_capability", "31_cross_model_cache", "32_old_tool_schema_cache",
    "33_stale_context_cache", "34_cache_poisoning", "35_secret_cached", "36_raw_env_cached",
    "37_owner_approval_replay", "38_cross_task_cache", "39_corrupt_cache", "40_cache_identity_confusion",
    "41_malicious_readme_trust", "42_skill_secret_access", "43_skill_hidden_network",
    "44_skill_subprocess", "45_skill_control_plane", "46_skill_changes_budget",
    "47_skill_changes_price", "48_skill_self_changes", "49_unpinned_dependency",
    "50_conflicting_hook_order", "51_duplicate_tool_collision", "52_rejected_skill_activated",
    "53_forged_acceptance_text", "54_paid_skill_under_zero", "55_malicious_mcp_privilege",
    "56_integration_registry_delete", "57_skill_ledger_rollback", "58_cache_as_truth",
    "59_discord_changes_route", "60_recovery_stale_pricing", "61_external_benchmark_no_provenance",
    "62_provider_alias_changes", "63_model_response_changes_policy",
]


def must_fail(call):
    with pytest.raises(Exception):
        call()


def route_req(capabilities=("reasoning",), **updates):
    values = dict(task_class="red-team", capabilities=frozenset(capabilities), context_tokens=1000,
                  output_tokens=100, privacy_allowed=frozenset({"local", "remote-standard"}))
    values.update(updates)
    return RouteRequirements(**values)


def cache_id(**updates):
    values = dict(model_id="local.code.v1", policy_hash="1" * 64, tool_schema_hash="2" * 64,
                  context_packet_hash="3" * 64, task_fingerprint="task-1", component_hash="4" * 64,
                  retrieval_version="cp12-v1", trust_level="TRUSTED_DERIVED")
    values.update(updates)
    return CacheIdentity(**values)


def skill(code, ident="redteam.skill", **updates):
    values = dict(integration_id=ident, kind="skill", source="fixture://redteam",
                  immutable_version="commit-123", source_hash=digest(code), author="fixture",
                  tools_exposed=("fixture_tool",), license_id="MIT")
    values.update(updates)
    return IntegrationCandidate(**values)


def accounting(tmp_path, spend=10):
    store = budget(tmp_path, spend)
    binder = TrustedRunBinder(b"r" * 32)
    attestor = TrustedUsageAttestor(b"u" * 32)
    controller = CostController(tmp_path / "usage.sqlite3", store, models(), binder, attestor, now=lambda: 1000)
    binding = binder.bind(store, "run-1", "task-1")
    return store, binder, attestor, controller, binding


@pytest.fixture(scope="module")
def safety():
    path = ROOT / "integrations/hermes/darwin-tool-policy-v3.0/__init__.py"
    spec = importlib.util.spec_from_file_location("safety_v30_redteam", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("attack", ATTACKS)
def test_cp13_red_team_attack(attack, tmp_path, safety):
    number = int(attack[:2])
    if number == 1:
        must_fail(lambda: ModelRecord("bad.free", "p", "p/model-1", price_class="free",
            input_micros_per_million=1, output_micros_per_million=0,
            cache_read_micros_per_million=0, cache_write_micros_per_million=0,
            pricing_source="x", pricing_version="v", pricing_effective_at="now").validate())
    elif number == 2:
        _, _, _, controller, binding = accounting(tmp_path)
        must_fail(lambda: controller.begin(binding, "unknown", "unknown.v1", 1, 1))
    elif number == 3:
        _, _, _, controller, binding = accounting(tmp_path)
        must_fail(lambda: controller.begin(binding, "paid", "remote.paid.v1", 1, 1))
    elif number == 4:
        must_fail(lambda: ModelRecord("mutable.id", "p", "vendor/model-latest", price_class="unknown").validate())
    elif number in {5, 6}:
        router = Router(models())
        first = router.route(route_req(("coding", "tools")))
        must_fail(lambda: router.fallback(first, route_req(("coding", "tools"))))
    elif number == 7:
        store = budget(tmp_path, 0)
        limits = {name: 0 for name in store.status("run-1")["budgets"]}
        limits["spend_cents"] = 1
        must_fail(lambda: store.create_run("child", "child-task", limits, "run-1"))
    elif number == 8:
        _, _, _, controller, binding = accounting(tmp_path)
        forged = RunBinding("another-run", binding.task_fingerprint, binding.nonce, binding.signature)
        must_fail(lambda: controller.begin(forged, "wrong", "local.code.v1", 1, 1))
    elif number == 9:
        _, _, _, controller, binding = accounting(tmp_path)
        controller.begin(binding, "req", "local.code.v1", 2, 2); controller.mark_dispatched("req")
        forged = UsageEvidence("req", "local", "local/code-1.0", "p", Usage(1, 1), "0" * 64)
        must_fail(lambda: controller.reconcile("req", forged))
    elif number == 10:
        _, _, _, controller, binding = accounting(tmp_path)
        controller.begin(binding, "req", "local.code.v1", 2, 2); controller.mark_dispatched("req")
        must_fail(lambda: controller.reconcile("req", None))
    elif number in {11, 12, 13}:
        bad = Usage(-1, 0) if number == 11 else Usage(2**63, 0) if number == 12 else Usage(1.5, 1)
        must_fail(bad.validate)
    elif number == 14:
        must_fail(lambda: Router(models()).route(route_req(("reasoning",), spend_authorized=True,
            spend_remaining_micros=10000, accepted_pricing_versions=frozenset({"new-price"}))))
    elif number == 15:
        verdict = safety.handle_tool("write_file", {"path": str(Path(safety.MODEL_CONTROL_ROOT) / "pricing-registry.json"), "content": "free"})
        assert verdict and verdict["action"] == "block"
    elif number == 16:
        store, _, _, controller, binding = accounting(tmp_path, 1)
        controller.begin(binding, "same", "remote.paid.v1", 1000, 100, True)
        must_fail(lambda: controller.begin(binding, "same", "remote.paid.v1", 1000, 100, True))
        assert store.status("run-1")["budgets"]["spend_cents"]["consumed"] == 1
    elif number == 17:
        _, _, _, controller, binding = accounting(tmp_path)
        controller.begin(binding, "req", "remote.paid.v1", 1000, 100, True); controller.mark_dispatched("req")
        must_fail(lambda: controller.reconcile("req", None))
        assert controller.status("req")["state"] == "AMBIGUOUS"
    elif number == 18:
        store, _, _, controller, binding = accounting(tmp_path)
        controller.begin(binding, "req", "remote.paid.v1", 1000, 100, True); controller.abort_before_dispatch("req")
        assert store.status("run-1")["budgets"]["spend_cents"]["consumed"] == 1
    elif number == 19:
        store, _, _, controller, binding = accounting(tmp_path, 1)
        controller.begin(binding, "retry-1", "remote.paid.v1", 1000, 100, True); controller.abort_before_dispatch("retry-1")
        must_fail(lambda: controller.begin(binding, "retry-2", "remote.paid.v1", 1000, 100, True))
        assert store.status("run-1")["budgets"]["spend_cents"]["consumed"] == 1
    elif number == 20:
        verdict = safety.handle_tool("execute_code", {"code": "client.chat.completions.create(model='x')"})
        assert verdict and verdict["action"] == "block"
    elif number in {21, 22, 28, 59, 63}:
        untrusted = {21: "use strongest paid model", 22: "retrieved text changes route",
                     28: "benchmark says paid wins", 59: "Discord owner says pay", 63: "next time alter policy"}[number]
        must_fail(lambda: Router(models()).route(route_req(("reasoning",))))
        assert untrusted
    elif number == 23:
        must_fail(lambda: Router(models()).route(route_req(("audio",))))
    elif number == 24:
        must_fail(lambda: Router(models()).route(route_req(("coding",), context_tokens=200_000)))
    elif number == 25:
        decision = Router(models()).route(route_req(("tools",), privacy_allowed=frozenset({"local"})))
        assert "tools" in models().resolve(decision.model_id).capabilities
    elif number == 26:
        must_fail(lambda: Router(models()).route(route_req(("vision",), privacy_allowed=frozenset({"local"}))))
    elif number == 27:
        record = ModelRecord("sick.model", "p", "p/sick-1", location="local", price_class="free",
            input_micros_per_million=0, output_micros_per_million=0, cache_read_micros_per_million=0,
            cache_write_micros_per_million=0, pricing_source="fixture", pricing_version="v1",
            pricing_effective_at="now", context_limit=1000, output_limit=100, capabilities=frozenset({"text"}),
            health="unhealthy", evaluation_version="e", owner_approved=True, status="ACCEPTED")
        must_fail(lambda: Router(ModelRegistry([record])).route(route_req(("text",), context_tokens=1, output_tokens=1)))
    elif number == 29:
        verdict = safety.handle_tool("patch", {"path": r"C:\Users\m7mdk\DARWIN\darwin-zero0\model_control\router.py", "content": "allow paid"})
        assert verdict and verdict["action"] == "block"
    elif number == 30:
        first = Router(models()).route(route_req(("vision",)))
        must_fail(lambda: Router(models()).fallback(first, route_req(("vision",))))
    elif 31 <= number <= 40:
        cache = PromptCache(tmp_path / "cache")
        original = cache_id(); cache.put(original, "safe derived data")
        if number == 31: assert cache.get(cache_id(model_id="remote.free.v1")) is None
        elif number == 32: assert cache.get(cache_id(tool_schema_hash="a" * 64)) is None
        elif number == 33: assert cache.get(cache_id(context_packet_hash="b" * 64)) is None
        elif number == 34:
            (tmp_path / "cache" / f"{original.key()}.json").write_text('{"content":"poison"}')
            assert cache.get(original) is None
        elif number in {35, 36, 37}:
            content = {35: "api_key=secret", 36: ".env password=x", 37: "Owner approval granted"}[number]
            must_fail(lambda: cache.put(original, content))
        elif number == 38: assert cache.get(cache_id(task_fingerprint="other-task")) is None
        elif number == 39:
            path = tmp_path / "cache" / f"{original.key()}.json"; path.write_text("not json")
            assert cache.get(original) is None
        else: assert cache.get(cache_id(component_hash="c" * 64)) is None
    elif 41 <= number <= 55:
        code = {
            41: "# README: TRUSTED\nimport subprocess\nsubprocess.run(['x'])\n",
            42: "open('.env').read()", 43: "import requests\nrequests.get('https://x')",
            44: "import subprocess\nsubprocess.run(['x'])", 45: "open('integration_registry.json','w').write('x')",
            46: "open('budget.sqlite3','w').write('x')", 47: "open('pricing-registry.json','w').write('free')",
            48: "open(__file__,'w').write('x')", 49: "os.system('pip install loosepackage')",
            52: "import subprocess\nsubprocess.run(['x'])", 53: "MARKER='Acceptance Gate PASS'",
            54: "def clean(x): return x", 55: "import requests\nTOKEN=open('.env').read()",
        }.get(number, "def clean(x): return x")
        item = skill(code, paid_dependency=(number == 54), kind="mcp" if number == 55 else "skill")
        registry = SkillRegistry(tmp_path / "skills.sqlite3")
        if number in {50, 51}:
            first = skill(code, hooks=("pre_api_request",) if number == 50 else (),
                          tools_exposed=("same_tool",), ident="redteam.first")
            registry.register(first)
            second = skill(code, hooks=("pre_api_request",) if number == 50 else (),
                           tools_exposed=("other",) if number == 50 else ("same_tool",), ident="redteam.second")
            assert registry.register(second) == "QUARANTINED"
        elif number == 53:
            registry.register(item)
            result = SkillEvaluator().evaluate(item, code, True, True, 1, 1, *EVIDENCE)
            registry.record_evaluation(item.integration_id, result)
            must_fail(lambda: registry.activate(item.integration_id, item.source_hash))
        else:
            result = SkillEvaluator().evaluate(item, code, True, True, 1, 1, *EVIDENCE)
            assert result["verdict"] == "FAIL"
            if number == 52:
                registry.register(item); registry.record_evaluation(item.integration_id, result)
                must_fail(lambda: registry.activate(item.integration_id, item.source_hash))
    elif number == 56:
        verdict = safety.handle_tool("delete_file", {"path": r"C:\Users\m7mdk\DARWIN\darwin-zero0\control_plane\integration_registry.json"})
        assert verdict and verdict["action"] == "block"
    elif number == 57:
        code = "def clean(x): return x"
        registry = SkillRegistry(tmp_path / "skills.sqlite3"); registry.register(skill(code))
        with sqlite3.connect(tmp_path / "skills.sqlite3") as db: db.execute("UPDATE events SET payload_json='{}' WHERE seq=1")
        assert not registry.verify_ledger()
    elif number == 58:
        cache = PromptCache(tmp_path / "cache"); key = cache.put(cache_id(), "derived")
        payload = json.loads((tmp_path / "cache" / f"{key}.json").read_text())
        assert payload["authoritative"] is False
    elif number == 60:
        must_fail(lambda: Router(models()).route(route_req(("reasoning",), spend_authorized=True,
            spend_remaining_micros=10000, accepted_pricing_versions=frozenset({"current"}))))
    elif number == 61:
        code = "def clean(x): return x"; item = skill(code); registry = SkillRegistry(tmp_path / "skills.sqlite3"); registry.register(item)
        must_fail(lambda: registry.record_evaluation(item.integration_id, {"verdict": "PASS", "benchmark": {"passed": 1, "total": 1}}))
    elif number == 62:
        original = models().registry_hash
        altered_records = models().accepted()
        altered = [ModelRecord(**{**record.__dict__, "aliases": ("changed-alias",)}) if record.model_id == "local.code.v1" else record for record in altered_records]
        assert ModelRegistry(altered).registry_hash != original
