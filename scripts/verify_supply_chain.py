from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
REMOTE_USES = re.compile(r"(?m)^\s*(?:-\s*)?uses\s*:\s*([^\s#]+)")
FORBIDDEN_EXEC = re.compile(
    r"(?mi)^\s*run\s*:\s*.*(?:curl|wget|iwr|invoke-webrequest|irm|invoke-restmethod).*(?:\||iex|invoke-expression)"
)

def load_registry(repo: Path) -> dict:
    obj = json.loads((repo / "control_plane" / "integration_registry.json").read_text(encoding="utf-8"))
    if obj.get("default_policy") != "deny":
        raise RuntimeError("Integration Registry must be default-deny")
    return obj

def registered_actions(registry: dict) -> set[tuple[str, str]]:
    result = set()
    for entry in registry.get("github_actions", {}).get("registered_actions", []):
        if not isinstance(entry, dict) or not entry.get("owner_approved"):
            continue
        action = str(entry.get("action") or "").casefold()
        commit = str(entry.get("commit_sha") or "").casefold()
        if not HEX40.fullmatch(commit):
            raise RuntimeError(f"registered Action is not pinned: {action}")
        result.add((action, commit))
    return result

def verify_workflow(path: Path, registry: dict) -> None:
    text = path.read_text(encoding="utf-8")
    low = text.casefold()
    if "pull_request_target:" in low:
        raise RuntimeError(f"pull_request_target forbidden: {path}")
    if re.search(r"(?m)^\s*permissions\s*:\s*write-all\s*$", low):
        raise RuntimeError(f"permissions: write-all forbidden: {path}")
    if re.search(r"(?mi)^\s*[a-z0-9_-]+\s*:\s*write\s*$", text):
        raise RuntimeError(f"individual write permission forbidden: {path}")
    if re.search(r"\$\{\{\s*secrets\.", text, re.I):
        raise RuntimeError(f"workflow secret access forbidden: {path}")
    if FORBIDDEN_EXEC.search(text):
        raise RuntimeError(f"remote download/execute forbidden: {path}")

    allowed = registered_actions(registry)
    for match in REMOTE_USES.finditer(text):
        value = match.group(1).strip().strip("'\"")
        if value.startswith("./"):
            continue
        if "@" not in value:
            raise RuntimeError(f"Action lacks pin: {value}")
        action, ref = value.rsplit("@", 1)
        if not HEX40.fullmatch(ref):
            raise RuntimeError(f"Action lacks full commit SHA: {value}")
        if (action.casefold(), ref.casefold()) not in allowed:
            raise RuntimeError(f"Action is pinned but unregistered: {value}")

def verify_repo(repo: Path) -> None:
    registry = load_registry(repo)
    workflow_dir = repo / ".github" / "workflows"
    workflows = sorted(list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml")))
    if not workflows:
        raise RuntimeError("no GitHub Actions workflows found")
    for path in workflows:
        verify_workflow(path, registry)

    if (repo / ".gitmodules").exists():
        raise RuntimeError(".gitmodules is not allowed without a dedicated registered-submodule policy")

    dep = repo / ".github" / "dependabot.yml"
    if not dep.is_file():
        raise RuntimeError("Dependabot config missing")
    if "package-ecosystem: github-actions" not in dep.read_text(encoding="utf-8").casefold():
        raise RuntimeError("Dependabot must monitor GitHub Actions")

    gt = repo / ".gitleaks.toml"
    if not gt.is_file() or "usedefault = true" not in gt.read_text(encoding="utf-8").casefold():
        raise RuntimeError("Gitleaks config must extend defaults")

    co = repo / ".github" / "CODEOWNERS"
    if not co.is_file() or "@mo7m1d" not in co.read_text(encoding="utf-8"):
        raise RuntimeError("CODEOWNERS missing canonical Owner")

def self_test() -> None:
    assert HEX40.fullmatch("a" * 40)
    assert not HEX40.fullmatch("v4")
    print("SUPPLY_CHAIN_VERIFIER_SELF_TEST=PASS")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.repo:
        raise SystemExit("--repo is required unless --self-test is used")
    verify_repo(Path(args.repo).resolve())
    print("DARWIN_SUPPLY_CHAIN_REPO_VERIFY=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
