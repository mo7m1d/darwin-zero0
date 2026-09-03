from __future__ import annotations

import ast
import ntpath
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

DARWIN_REPO = r"C:\Users\m7mdk\DARWIN\darwin-zero0"
HERMES_CONFIG = r"C:\Users\m7mdk\AppData\Local\hermes\config.yaml"
POLICY_ROOT = str(Path(__file__).resolve().parent)
HERMES_HOME = str(Path(__file__).resolve().parents[2])
TELEMETRY_ROOT = str(Path(HERMES_HOME) / "darwin" / "telemetry")
TELEMETRY_PLUGIN_ROOT = str(Path(HERMES_HOME) / "plugins" / "darwin-runtime-telemetry")
CONTROL_PLANE_BACKUP_ROOT = str(Path(HERMES_HOME) / "backups" / "control-plane")
SUPERVISOR_ROOT = str(Path(HERMES_HOME) / "darwin" / "supervisor")
SUPERVISOR_PLUGIN_ROOT = str(Path(HERMES_HOME) / "plugins" / "darwin-control-supervisor")
ACCEPTANCE_ROOT = str(Path(HERMES_HOME) / "darwin" / "acceptance")
ACCEPTANCE_PLUGIN_ROOT = str(Path(HERMES_HOME) / "plugins" / "darwin-acceptance-gate")
GIT_SUPPLY_PLUGIN_ROOT = str(Path(HERMES_HOME) / "plugins" / "darwin-git-supply-gate")
RECOVERY_ROOT = str(Path(HERMES_HOME) / "darwin" / "recovery")
RECOVERY_REPO_ROOT = str(Path(DARWIN_REPO) / "recovery")
RECOVERY_PROTOCOL = str(Path(DARWIN_REPO) / "protocols" / "RECOVERY_CHECKPOINT_PROTOCOL.md")
POLICY_MODE = os.environ.get("DARWIN_TOOL_POLICY_MODE", "ENFORCE").strip().upper()
if POLICY_MODE not in {"OFF", "AUDIT", "ENFORCE"}:
    POLICY_MODE = "ENFORCE"

PROTECTED_REPO_BASENAMES = {"agents.md", "darwin_bootstrap.md", "darwin_constitution.md", "owner_constitution.md", "constitution.md", "owner_approval_matrix.json", "readiness_gate.json"}
OWNER_CONSTITUTION_BASENAMES = {"darwin_constitution.md", "owner_constitution.md", "constitution.md"}
PROTECTED_REPO_RELATIVE_ROOTS = ("control_plane", r"core\control_plane")
CONTROL_PLANE_TEXT_MARKERS = ("darwin-tool-policy", "darwin-runtime-telemetry", "darwin-control-supervisor", "darwin-acceptance-gate", "darwin-git-supply-gate", "integration_registry.json", "events.sqlite3", "decisions.sqlite3", "acceptance.sqlite3", "owner_constitution", "owner_approval_matrix", "readiness_gate")
CONTROL_PLANE_TEXT_MARKERS = CONTROL_PLANE_TEXT_MARKERS + ("darwin-recovery-manager", "checkpoint-ledger.jsonl", "recovery-knowledge.json", "retry-history.json", "runtime-profile", "darwin\\recovery")
HEREDOC_RE = re.compile(r"<<-?\s*['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?", re.IGNORECASE)
SED_INPLACE_RE = re.compile(r"(?:^|[;&|]\s*|\s)\bsed\b[^\r\n]*\s-i(?:\s|$)", re.IGNORECASE)
SHELL_DELETE_RE = re.compile(
    r"(?:^|[;&|]\s*|\s)(?:rm(?:\.exe)?\b|rmdir\b|del\b|erase\b|remove-item\b)",
    re.IGNORECASE,
)
GIT_DESTRUCTIVE_RE = re.compile(
    r"\bgit\s+(?:clean\b|reset\s+--hard\b|restore\b|checkout\s+--\b)",
    re.IGNORECASE,
)
BULK_REWRITE_RE = re.compile(
    r"(?:\bfor\b.+\b(?:write|open|set-content|out-file)\b|"
    r"\b(?:tee|set-content|out-file|add-content)\b|"
    r"(?:^|\s)(?:>|>>)\s*[\"']?[A-Za-z0-9_.\\/:-]+)",
    re.IGNORECASE | re.DOTALL,
)
ABS_WIN_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^'\"\r\n\t )}\]]+")

PY_MUTATING_CALLS = {
    "os.remove", "os.unlink", "os.rename", "os.replace", "os.rmdir",
    "shutil.move", "shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.rmtree",
}
PATH_MUTATING_METHODS = {"write_text", "write_bytes", "unlink", "rename", "replace", "rmdir"}

def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", handle_tool)

def handle_tool(tool_name: str = "", args: Any = None, **_: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(args, dict):
        args = {}

    owner_directive = _owner_constitution_directive((tool_name or "").lower(), args)
    if owner_directive is not None:
        return owner_directive

    if POLICY_MODE == "OFF":
        return None
    try:
        reason = _decision_reason((tool_name or "").lower(), args)
    except Exception as exc:
        if _mutation_capable_tool((tool_name or "").lower(), args):
            return _emit(
                "POLICY_ANALYSIS_FAILURE",
                f"Safety analysis failed for a mutation-capable action ({type(exc).__name__}).",
            )
        return None
    if not reason:
        return None
    if POLICY_MODE == "AUDIT":
        return None
    return _emit(*reason)

def _owner_constitution_directive(tool_name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # Direct Constitution mutation is a true Owner boundary, but only through
    # the narrow write_file/patch path. Terminal/execute_code/bulk mechanisms
    # remain subject to the existing hard Safety Kernel blocks.
    if tool_name not in {"write_file", "patch"}:
        return None

    cwd = _cwd(args)
    for path in _direct_paths(args):
        normalized = _norm(path, cwd)
        if not _inside(path, DARWIN_REPO, cwd):
            continue
        basename = ntpath.basename(normalized).casefold()
        if basename not in OWNER_CONSTITUTION_BASENAMES:
            continue
        return {
            "action": "approve",
            "message": (
                "DARWIN OWNER DECISION [constitution_change]. "
                "A protected Constitution control file would be modified through "
                "the narrow write/patch path. Approve only if this exact change is "
                "intended. Fresh one-operation Owner approval is mandatory."
            ),
            "rule_key": f"darwin.owner.v1:constitution_change:{basename}",
            "force_human_once": True,
        }
    return None


def _emit(reason_code: str, detail: str) -> Dict[str, str]:
    decision_id = uuid.uuid4().hex[:12]
    return {
        "action": "block",
        "message": (
            f"BLOCKED BY DARWIN TOOL POLICY [{reason_code}] decision={decision_id}. "
            f"{detail} Use read_file/search_files -> minimal patch/write_file -> "
            "py_compile -> targeted pytest, or escalate for Owner approval."
        ),
    }

def _decision_reason(tool_name: str, args: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    if _targets_control_plane(args) and _mutation_capable_tool(tool_name, args):
        return ("CONTROL_PLANE_SELF_PROTECTION",
                "Darwin may not directly mutate protected control-plane files.")

    if tool_name in {"delete_file", "remove_file", "unlink_file"} and _targets_darwin(args):
        return ("SOURCE_OR_STATE_DELETE",
                "Direct deletion inside the protected DARWIN workspace is not allowed.")

    if tool_name == "terminal":
        command = _arg_text(args, "command")
        if not _targets_darwin(args, text=command):
            return None
        if HEREDOC_RE.search(command):
            return ("HEREDOC_MUTATION", "Heredoc/here-document project mutation is forbidden.")
        if SED_INPLACE_RE.search(command):
            return ("SED_INPLACE", "sed -i project mutation is forbidden.")
        if SHELL_DELETE_RE.search(command):
            return ("SHELL_DELETE", "Destructive shell deletion inside DARWIN is forbidden.")
        if GIT_DESTRUCTIVE_RE.search(command):
            return ("GIT_DESTRUCTIVE", "Destructive Git workspace reset/clean/restore is forbidden.")
        if BULK_REWRITE_RE.search(command):
            return ("BULK_SCRIPT_REWRITE", "Bulk shell/project rewrite mechanisms are forbidden.")
        if _terminal_embeds_mutating_python(command):
            return ("SCRIPTED_FILE_MUTATION", "Scripted filesystem mutation through the terminal is forbidden.")
        return None

    if tool_name == "execute_code":
        code = _arg_text(args, "code")
        mutation = _python_any_mutation_kind(code)
        if mutation:
            return ("EXECUTE_CODE_FILE_MUTATION",
                    f"execute_code filesystem/process mutation detected ({mutation}).")
        return None

    return None

def _mutation_capable_tool(tool_name: str, args: Dict[str, Any]) -> bool:
    if tool_name in {"terminal", "execute_code", "write_file", "patch", "delete_file", "remove_file", "unlink_file"}:
        return True
    text = " ".join(str(v) for v in args.values() if isinstance(v, (str, int, float)))
    return bool(re.search(r"\b(delete|remove|write|patch|rename|move|replace)\b", text, re.I))

def _arg_text(args: Dict[str, Any], key: str) -> str:
    value = args.get(key, "")
    return value if isinstance(value, str) else str(value or "")

def _cwd(args: Dict[str, Any]) -> str:
    for key in ("cwd", "workdir", "working_directory"):
        value = args.get(key)
        if isinstance(value, str) and value:
            return value
    return ""

def _norm(path: str, cwd: str = "") -> str:
    if not path:
        return ""
    value = str(path).strip().strip('"').strip("'").replace("/", "\\")
    if cwd and not ntpath.isabs(value):
        value = ntpath.join(cwd.replace("/", "\\"), value)
    return ntpath.normcase(ntpath.normpath(value))

def _inside(path: str, root: str, cwd: str = "") -> bool:
    p = _norm(path, cwd)
    r = _norm(root)
    if not p:
        return False
    try:
        return ntpath.commonpath([p, r]) == r
    except ValueError:
        return False

def _absolute_paths(text: str) -> Iterable[str]:
    return ABS_WIN_PATH_RE.findall(text or "")

def _direct_paths(args: Dict[str, Any]) -> Iterable[str]:
    for key in ("path", "file", "file_path", "target", "destination", "src", "dst", "source", "old_path", "new_path"):
        value = args.get(key)
        if isinstance(value, str) and value:
            yield value

def _targets_darwin(args: Dict[str, Any], text: str = "") -> bool:
    cwd = _cwd(args)
    for p in _direct_paths(args):
        if _inside(p, DARWIN_REPO, cwd):
            return True
    for p in _absolute_paths(text):
        if _inside(p, DARWIN_REPO):
            return True
    folded = (text or "").replace("/", "\\").casefold()
    if DARWIN_REPO.replace("/", "\\").casefold() in folded:
        return True
    if _inside(cwd, DARWIN_REPO):
        absolute = list(_absolute_paths(text))
        if not absolute:
            return True
        return any(_inside(p, DARWIN_REPO) for p in absolute)
    return False


def _repo_control_path(path: str, cwd: str = "") -> bool:
    normalized = _norm(path, cwd)
    repo = _norm(DARWIN_REPO)
    if not normalized or not _inside(normalized, repo):
        return False
    try:
        rel = ntpath.relpath(normalized, repo)
    except ValueError:
        return False
    rel_folded = rel.replace("/", "\\").casefold()
    for root in PROTECTED_REPO_RELATIVE_ROOTS:
        root_folded = root.replace("/", "\\").casefold()
        if rel_folded == root_folded or rel_folded.startswith(root_folded + "\\"):
            return True
    return False

def _targets_control_plane(args: Dict[str, Any]) -> bool:
    cwd = _cwd(args)
    text_parts = []
    for key in ("command", "code", "content", "new_content", "old_content"):
        value = args.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    text = "\n".join(text_parts)

    protected_roots = (
        POLICY_ROOT,
        TELEMETRY_ROOT,
        TELEMETRY_PLUGIN_ROOT,
        CONTROL_PLANE_BACKUP_ROOT,
        SUPERVISOR_ROOT,
        SUPERVISOR_PLUGIN_ROOT,
        ACCEPTANCE_ROOT,
        ACCEPTANCE_PLUGIN_ROOT,
        GIT_SUPPLY_PLUGIN_ROOT,
        RECOVERY_ROOT,
        RECOVERY_REPO_ROOT,
        RECOVERY_PROTOCOL,
    )

    if any(_inside(cwd, root) for root in protected_roots):
        return True

    for p in _direct_paths(args):
        normalized = _norm(p, cwd)
        if normalized == _norm(HERMES_CONFIG):
            return True
        if any(_inside(p, root, cwd) for root in protected_roots):
            return True
        if _inside(p, DARWIN_REPO, cwd):
            if ntpath.basename(normalized).casefold() in PROTECTED_REPO_BASENAMES:
                return True
            if _repo_control_path(p, cwd):
                return True

    folded = text.replace("/", "\\").casefold()
    if HERMES_CONFIG.replace("/", "\\").casefold() in folded:
        return True
    for root in protected_roots:
        if root.replace("/", "\\").casefold() in folded:
            return True
    if any(marker in folded for marker in CONTROL_PLANE_TEXT_MARKERS):
        return True

    for p in _absolute_paths(text):
        if any(_inside(p, root) for root in protected_roots):
            return True
        if _repo_control_path(p):
            return True

    if _targets_darwin(args, text=text):
        if any(name in folded for name in PROTECTED_REPO_BASENAMES):
            return True
        if any(root.replace("/", "\\").casefold() in folded for root in PROTECTED_REPO_RELATIVE_ROOTS):
            return True
    return False

def _terminal_embeds_mutating_python(command: str) -> bool:
    low = command.casefold()
    if "python" not in low:
        return False
    markers = (
        "write_text(", "write_bytes(", "open(", "os.remove(", "os.unlink(",
        "os.rename(", "os.replace(", "shutil.rmtree(", "shutil.move(", "shutil.copy(",
    )
    return any(m in low for m in markers)


def _python_any_mutation_kind(code: str) -> str:
    if not code.strip():
        return ""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        low = code.casefold()
        markers = (
            ".write_text(", ".write_bytes(", "open(", "os.remove(", "os.unlink(",
            "os.rename(", "os.replace(", "os.rmdir(", "shutil.rmtree(", "shutil.move(",
            "shutil.copy(", "shutil.copy2(", "shutil.copyfile(", "subprocess.run(",
            "subprocess.call(", "subprocess.popen(", "os.system(", "sqlite3.connect(",
        )
        return "textual-mutation-marker" if any(m in low for m in markers) else ""

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)

        if name == "open":
            mode = _literal_str(node.args[1]) if len(node.args) >= 2 else ""
            if not mode:
                for kw in node.keywords:
                    if kw.arg == "mode":
                        mode = _literal_str(kw.value)
            if mode and any(ch in mode for ch in ("w", "a", "x", "+")):
                return f"open:{mode}"

        if name in PY_MUTATING_CALLS:
            return name

        if name in {
            "subprocess.run", "subprocess.call", "subprocess.Popen",
            "subprocess.check_call", "os.system",
        }:
            return name

        if isinstance(node.func, ast.Attribute) and node.func.attr in PATH_MUTATING_METHODS:
            return f"Path.{node.func.attr}"

        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "execute", "executemany", "executescript",
        }:
            sql = _literal_str(node.args[0]) if node.args else ""
            if sql and re.match(
                r"(?is)^\s*(insert|update|delete|drop|alter|create|replace|vacuum|attach|detach|reindex)\b",
                sql,
            ):
                return f"sql:{node.func.attr}"
    return ""

def _python_mutation_kind(code: str, cwd: str) -> str:
    if not code.strip():
        return ""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        low = code.casefold()
        if any(token in low for token in (
            ".write_text(", ".write_bytes(", "os.remove(", "os.unlink(",
            "os.rename(", "os.replace(", "shutil.rmtree(", "shutil.move(",
        )):
            return "textual-mutation-marker"
        return ""

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)

        if name == "open":
            mode = _literal_str(node.args[1]) if len(node.args) >= 2 else ""
            if not mode:
                for kw in node.keywords:
                    if kw.arg == "mode":
                        mode = _literal_str(kw.value)
            if mode and any(ch in mode for ch in ("w", "a", "x", "+")):
                target = _literal_str(node.args[0]) if node.args else ""
                if _literal_target_is_protected(target, cwd):
                    return f"open:{mode}"
                if not target and _inside(cwd, DARWIN_REPO):
                    return f"open:{mode}:dynamic-target"

        if name in PY_MUTATING_CALLS:
            target = _literal_str(node.args[0]) if node.args else ""
            if _literal_target_is_protected(target, cwd):
                return name
            if not target and _inside(cwd, DARWIN_REPO):
                return f"{name}:dynamic-target"

        if isinstance(node.func, ast.Attribute) and node.func.attr in PATH_MUTATING_METHODS:
            target = _path_constructor_literal(node.func.value)
            if _literal_target_is_protected(target, cwd):
                return f"Path.{node.func.attr}"
            if not target and _inside(cwd, DARWIN_REPO):
                return f"Path.{node.func.attr}:dynamic-target"
    return ""

def _literal_target_is_protected(target: str, cwd: str) -> bool:
    if not target:
        return False
    return (
        _inside(target, DARWIN_REPO, cwd)
        or _inside(target, POLICY_ROOT, cwd)
        or _inside(target, TELEMETRY_ROOT, cwd)
        or _inside(target, TELEMETRY_PLUGIN_ROOT, cwd)
        or _inside(target, CONTROL_PLANE_BACKUP_ROOT, cwd)
        or _inside(target, SUPERVISOR_ROOT, cwd)
        or _inside(target, SUPERVISOR_PLUGIN_ROOT, cwd)
        or _inside(target, ACCEPTANCE_ROOT, cwd)
        or _inside(target, ACCEPTANCE_PLUGIN_ROOT, cwd)
        or _inside(target, GIT_SUPPLY_PLUGIN_ROOT, cwd)
        or _inside(target, RECOVERY_ROOT, cwd)
        or _inside(target, RECOVERY_REPO_ROOT, cwd)
        or _norm(target, cwd) == _norm(RECOVERY_PROTOCOL)
        or _norm(target, cwd) == _norm(HERMES_CONFIG)
    )

def _call_name(func: ast.AST) -> str:
    parts = []
    cur = func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))

def _literal_str(node: ast.AST) -> str:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""

def _path_constructor_literal(node: ast.AST) -> str:
    if isinstance(node, ast.Call) and _call_name(node.func) in {"Path", "pathlib.Path"} and node.args:
        return _literal_str(node.args[0])
    return ""
