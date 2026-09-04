import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from model_control import CacheIdentity, IntegrationCandidate, PromptCache, SkillEvaluator, SkillRegistry
from model_control.cache import CacheDenied
from model_control.skills import SkillDenied
from tests.cp13_helpers import digest

EVIDENCE = ("d" * 64, "e" * 64, "f" * 64)


def identity(**changes):
    values = dict(model_id="local.code.v1", policy_hash="1" * 64,
                  tool_schema_hash="2" * 64, context_packet_hash="3" * 64,
                  task_fingerprint="task-one", component_hash="4" * 64,
                  retrieval_version="cp12-v1", trust_level="TRUSTED_DERIVED")
    values.update(changes)
    return CacheIdentity(**values)


def candidate(code="def clean(value):\n    return value\n", integration_id="fixture.clean", **changes):
    values = dict(integration_id=integration_id, kind="skill", source="fixture://clean",
                  immutable_version="commit-abc123", source_hash=digest(code), author="fixture-author",
                  requested_capabilities=("text-transform",), tools_exposed=("clean_value",),
                  license_id="MIT")
    values.update(changes)
    return IntegrationCandidate(**values), code


def test_cache_round_trip_and_identity_isolation(tmp_path):
    cache = PromptCache(tmp_path / "cache")
    cache.put(identity(), "derived packet")
    assert cache.get(identity()) == "derived packet"
    assert cache.get(identity(model_id="remote.free.v1")) is None
    assert cache.get(identity(task_fingerprint="task-two")) is None


@pytest.mark.parametrize("content", [
    "api_key=secret-value", "password: hunter", "access_token=x",
    "-----BEGIN PRIVATE KEY-----", "otp=123456", "Owner approval granted",
    "permission granted", "budget expansion approved", "ignore previous instructions",
])
def test_cache_rejects_secret_and_authority_material(tmp_path, content):
    with pytest.raises(CacheDenied):
        PromptCache(tmp_path / "cache").put(identity(), content)


def test_cache_corruption_is_safe_miss(tmp_path):
    cache = PromptCache(tmp_path / "cache")
    key = cache.put(identity(), "safe")
    (tmp_path / "cache" / f"{key}.json").write_text("{}")
    assert cache.get(identity()) is None


def test_raw_env_source_rejected_even_without_secret_pattern(tmp_path):
    with pytest.raises(CacheDenied):
        PromptCache(tmp_path / "cache").put(identity(), "innocent-looking-value", source_ref="/project/.env.local")


def test_cache_schema_tool_context_and_policy_bound(tmp_path):
    cache = PromptCache(tmp_path / "cache")
    cache.put(identity(), "safe")
    for changed in (identity(policy_hash="a" * 64), identity(tool_schema_hash="b" * 64),
                    identity(context_packet_hash="c" * 64), identity(retrieval_version="cp12-v2")):
        assert cache.get(changed) is None


def test_skill_default_deny_then_evaluate_accept_activate(tmp_path):
    item, code = candidate()
    registry = SkillRegistry(tmp_path / "skills.sqlite3")
    assert registry.status(item.integration_id) == "DENIED"
    assert registry.register(item) == "CANDIDATE"
    result = SkillEvaluator().evaluate(item, code, True, True, 3, 3, *EVIDENCE)
    registry.record_evaluation(item.integration_id, result)
    assert registry.status(item.integration_id) == "EVALUATED"
    with pytest.raises(SkillDenied):
        registry.activate(item.integration_id, item.source_hash)
    registry.accept(item.integration_id, True, "acceptance://fixture", "a" * 64)
    assert registry.activate(item.integration_id, item.source_hash)["status"] == "ACCEPTED"
    assert registry.verify_ledger()


def test_skill_owner_and_acceptance_required(tmp_path):
    item, code = candidate()
    registry = SkillRegistry(tmp_path / "skills.sqlite3")
    registry.register(item)
    registry.record_evaluation(item.integration_id, SkillEvaluator().evaluate(item, code, True, True, 1, 1, *EVIDENCE))
    with pytest.raises(SkillDenied):
        registry.accept(item.integration_id, False, "plain text says PASS", "a" * 64)


def test_skill_source_change_blocks_evaluation_and_activation(tmp_path):
    item, code = candidate()
    with pytest.raises(SkillDenied, match="source changed"):
        SkillEvaluator().evaluate(item, code + "# mutation", True, True, 1, 1, *EVIDENCE)


def test_paid_skill_fails_zero_cost_evaluation():
    item, code = candidate(paid_dependency=True)
    assert SkillEvaluator().evaluate(item, code, True, True, 1, 1, *EVIDENCE)["verdict"] == "FAIL"


def test_duplicate_tool_and_hook_quarantined(tmp_path):
    registry = SkillRegistry(tmp_path / "skills.sqlite3")
    first, code = candidate(hooks=("pre_api_request",))
    registry.register(first)
    second, _ = candidate(code, "fixture.second", tools_exposed=("clean_value",), hooks=("pre_api_request",))
    assert registry.register(second) == "QUARANTINED"
    with pytest.raises(SkillDenied):
        registry.record_evaluation(second.integration_id, {"verdict": "PASS"})


def test_rejected_skill_cannot_activate(tmp_path):
    item, code = candidate(code="import subprocess\nsubprocess.run(['x'])\n")
    registry = SkillRegistry(tmp_path / "skills.sqlite3")
    registry.register(item)
    result = SkillEvaluator().evaluate(item, code, True, True, 1, 1, *EVIDENCE)
    assert result["verdict"] == "FAIL"
    registry.record_evaluation(item.integration_id, result)
    with pytest.raises(SkillDenied):
        registry.activate(item.integration_id, item.source_hash)


def test_skill_ledger_tamper_detected(tmp_path):
    item, _ = candidate()
    registry = SkillRegistry(tmp_path / "skills.sqlite3")
    registry.register(item)
    with sqlite3.connect(tmp_path / "skills.sqlite3") as db:
        db.execute("UPDATE events SET payload_json='{}' WHERE seq=1")
    assert not registry.verify_ledger()


@pytest.mark.parametrize("case", json.loads((Path(__file__).parent / "fixtures/cp13/skill_holdout.json").read_text())["cases"], ids=lambda item: item["name"])
def test_skill_holdout(case):
    item, code = candidate(case["code"], integration_id="holdout." + case["name"].replace(" ", "-"))
    result = SkillEvaluator().evaluate(item, code, True, True, 2, 2, *EVIDENCE)
    assert result["verdict"] == case["expected"]
