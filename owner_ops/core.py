from __future__ import annotations
import copy
import re
import time
from typing import Any, Callable, Mapping
from .model import ControlRequest

class OwnerOpsError(RuntimeError):
    pass

SECRET_KEY = re.compile(r"(?:secret|password|passwd|token|api[_-]?key|private[_-]?key|otp|credential|authorization)", re.I)
SECRET_VALUE = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)", re.I)
SAFE_SECTIONS = ("system", "task", "control", "budget", "model", "recovery", "context", "git", "security")

def scrub(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:128]:
            name = str(key)
            out[name] = "[REDACTED]" if SECRET_KEY.search(name) else scrub(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [scrub(item, depth + 1) for item in list(value)[:128]]
    if isinstance(value, str):
        text = value[:4096]
        return "[REDACTED]" if SECRET_VALUE.search(text) else text
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:1024]

class OwnerOpsReadModel:
    # Derived read model only. Source readers remain authoritative.
    def __init__(self, readers: Mapping[str, Callable[[], Mapping[str, Any]]], clock=None):
        unknown = set(readers) - set(SAFE_SECTIONS)
        if unknown:
            raise OwnerOpsError(f"unknown source sections: {sorted(unknown)!r}")
        self.readers = dict(readers)
        self.clock = clock or time.time

    def snapshot(self) -> dict[str, Any]:
        sections, errors = {}, {}
        for section in SAFE_SECTIONS:
            reader = self.readers.get(section)
            if reader is None:
                sections[section] = {"status": "UNKNOWN"}
                continue
            try:
                raw = reader()
                if not isinstance(raw, Mapping):
                    raise OwnerOpsError("reader returned non-mapping")
                sections[section] = scrub(copy.deepcopy(dict(raw)))
            except Exception as exc:
                sections[section] = {"status": "UNKNOWN"}
                errors[section] = type(exc).__name__
        return {
            "schema": "darwin.owner-ops.snapshot.v1",
            "generated_at": int(self.clock()),
            "canonical_truth": False,
            "sections": sections,
            "source_errors": errors,
        }

class ControlDispatcher:
    # Calls narrow existing control-plane callbacks; never edits their DBs.
    def __init__(self, callbacks: Mapping[str, Callable[[ControlRequest], Any]]):
        self.callbacks = dict(callbacks)

    def dispatch(self, request: ControlRequest) -> dict[str, Any]:
        request.validate()
        callback = self.callbacks.get(request.action)
        if callback is None:
            raise OwnerOpsError("control action is not wired")
        result = callback(request)
        return {
            "request_id": request.request_id,
            "action": request.action,
            "status": "ACCEPTED_BY_CONTROL_PATH",
            "result": scrub(result),
        }
