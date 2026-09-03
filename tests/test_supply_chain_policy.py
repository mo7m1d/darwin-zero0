from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_supply_chain.py"
spec = importlib.util.spec_from_file_location("supply_verify", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

def test_registry_default_deny_and_action_pins():
    reg = mod.load_registry(ROOT)
    assert reg["default_policy"] == "deny"
    actions = mod.registered_actions(reg)
    assert ("actions/checkout", "11d5960a326750d5838078e36cf38b85af677262") in actions
    assert ("gitleaks/gitleaks-action", "ff98106e4c7b2bc287b24eaf42907196329070c7") in actions

def test_repo_supply_chain_policy_passes():
    mod.verify_repo(ROOT)

def test_action_ref_must_be_full_sha(tmp_path):
    reg = mod.load_registry(ROOT)
    wf = tmp_path / "bad.yml"
    wf.write_text("steps:\n  - uses: actions/checkout@v4\n", encoding="utf-8")
    try:
        mod.verify_workflow(wf, reg)
    except RuntimeError as exc:
        assert "full commit SHA" in str(exc)
    else:
        raise AssertionError("unpinned action unexpectedly passed")

def test_pinned_but_unregistered_action_fails(tmp_path):
    reg = mod.load_registry(ROOT)
    wf = tmp_path / "bad.yml"
    wf.write_text("steps:\n  - uses: evil/action@" + ("a" * 40) + "\n", encoding="utf-8")
    try:
        mod.verify_workflow(wf, reg)
    except RuntimeError as exc:
        assert "unregistered" in str(exc)
    else:
        raise AssertionError("unregistered action unexpectedly passed")

def test_ci_write_permissions_fail(tmp_path):
    reg = mod.load_registry(ROOT)
    wf = tmp_path / "bad.yml"
    wf.write_text("permissions:\n  contents: write\n", encoding="utf-8")
    try:
        mod.verify_workflow(wf, reg)
    except RuntimeError as exc:
        assert "write permission" in str(exc)
    else:
        raise AssertionError("write permission unexpectedly passed")
