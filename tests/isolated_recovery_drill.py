from __future__ import annotations

import json
import tempfile
from pathlib import Path

from recovery.runtime_integration import IntegratedRecoveryManager, build_candidate_profile, file_sha256


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="darwin-cp10-prepromotion-drill-") as td:
        root=Path(td); registry=root/"registry.json"; registry.write_text("{}\n",encoding="utf-8")
        profile=build_candidate_profile(state_root=root/"isolated-state",checkpoint_root=root/"isolated-store",live_hermes_home=root/"never-live",canonical_head="a"*64,hermes_head="b"*64,plugin_versions={"darwin-tool-policy":"2.6.0"},approvals_mode="manual",integration_registry_ref=str(registry),integration_registry_sha256=file_sha256(registry))
        entry=next(x for x in profile["entries"] if x["id"]=="kanban_board_metadata"); target=Path(entry["path"]); target.parent.mkdir(parents=True); target.write_text('{"state":"before"}\n',encoding="utf-8")
        manager=IntegratedRecoveryManager(profile); before=file_sha256(target); manager.create_checkpoint("drill",["kanban_board_metadata"],["drill:isolated"]); target.write_text('{"state":"after"}\n',encoding="utf-8"); current=file_sha256(target)
        manager.restore_checkpoint("drill",expected_current_hashes={"kanban_board_metadata:board.json":current},owner_authorized=True)
        if file_sha256(target)!=before: return 1
    print("ISOLATED_RECOVERY_DRILL=PASS")
    return 0

if __name__ == "__main__": raise SystemExit(main())
