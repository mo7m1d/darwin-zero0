from __future__ import annotations

import hashlib

from model_control import ModelRecord, ModelRegistry
from run_control import BudgetStore


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def models() -> ModelRegistry:
    common = dict(enabled=True, pricing_source="owner-reviewed-fixture",
                  pricing_version="2026-09-04.v1", pricing_effective_at="2026-09-04T00:00:00Z",
                  context_limit=100_000, output_limit=20_000, evaluation_version="eval-v1",
                  owner_approved=True, status="ACCEPTED", health="healthy")
    return ModelRegistry([
        ModelRecord("local.code.v1", "local", "local/code-1.0", aliases=("safe-local",),
                    location="local", price_class="free", input_micros_per_million=0,
                    output_micros_per_million=0, cache_read_micros_per_million=0,
                    cache_write_micros_per_million=0, capabilities=frozenset({"text", "tools", "coding", "structured"}),
                    coding_class=75, latency_class=20, privacy_class="local", reliability=85, **common),
        ModelRecord("remote.free.v1", "remote-free", "vendor/free-1.2", location="remote",
                    price_class="free", input_micros_per_million=0, output_micros_per_million=0,
                    cache_read_micros_per_million=0, cache_write_micros_per_million=0,
                    capabilities=frozenset({"text", "vision", "structured"}), coding_class=50,
                    latency_class=35, privacy_class="remote-standard", reliability=80, **common),
        ModelRecord("remote.paid.v1", "remote-paid", "vendor/pro-2.1", location="remote",
                    price_class="paid", input_micros_per_million=1_000_000,
                    output_micros_per_million=2_000_000, cache_read_micros_per_million=100_000,
                    cache_write_micros_per_million=1_250_000,
                    capabilities=frozenset({"text", "vision", "tools", "coding", "structured", "reasoning"}),
                    coding_class=95, latency_class=30, privacy_class="remote-standard", reliability=95, **common),
        ModelRecord("unknown.v1", "unknown", "vendor/unknown-1.0", location="remote",
                    price_class="unknown", capabilities=frozenset({"text"}), coding_class=60,
                    latency_class=40, privacy_class="remote-standard", reliability=70,
                    context_limit=100_000, output_limit=20_000, evaluation_version="eval-v1",
                    owner_approved=True, status="ACCEPTED"),
    ])


def budget(tmp_path, spend_cents=0):
    store = BudgetStore(tmp_path / "budget.sqlite3", clock=lambda: 1_000)
    limits = {name: 100 for name in (
        "tool_calls_total", "mutation_tool_calls", "network_tool_calls",
        "external_effect_actions", "recovery_attempts", "candidate_rebuilds",
        "wall_clock_seconds", "child_runs")}
    limits["spend_cents"] = spend_cents
    store.create_run("run-1", "task-1", limits)
    return store
