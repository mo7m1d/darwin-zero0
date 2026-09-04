import sqlite3
import threading

import pytest

from model_control import CostController, CostDenied, TrustedRunBinder, TrustedUsageAttestor, Usage
from model_control.accounting import RunBinding
from tests.cp13_helpers import budget, models


def setup(tmp_path, spend=0):
    store = budget(tmp_path, spend)
    binder = TrustedRunBinder(b"k" * 32)
    attestor = TrustedUsageAttestor(b"u" * 32)
    controller = CostController(tmp_path / "usage.sqlite3", store, models(), binder, attestor, now=lambda: 1000)
    binding = binder.bind(store, "run-1", "task-1")
    return store, binder, attestor, controller, binding


def test_zero_cost_call_reconciles_authoritative_usage(tmp_path):
    _, _, attestor, controller, binding = setup(tmp_path)
    reservation = controller.begin(binding, "req-1", "local.code.v1", 1000, 100)
    assert reservation["reserved_micros"] == 0
    controller.mark_dispatched("req-1")
    assert controller.reconcile("req-1", attestor.attest("req-1", "local", "local/code-1.0", "provider-1", Usage(900, 90))) == 0
    assert controller.status("req-1")["state"] == "RECONCILED"
    assert controller.verify_ledger()


def test_default_zero_blocks_paid_reservation(tmp_path):
    _, _, _, controller, binding = setup(tmp_path)
    with pytest.raises(CostDenied, match="OWNER_DECISION"):
        controller.begin(binding, "paid", "remote.paid.v1", 1000, 100)
    with pytest.raises(Exception):
        controller.begin(binding, "paid", "remote.paid.v1", 1000, 100, owner_spend_authorized=True)


def test_paid_reserves_cp11_and_reconciles_exact_micros(tmp_path):
    store, _, attestor, controller, binding = setup(tmp_path, 10)
    reservation = controller.begin(binding, "paid", "remote.paid.v1", 1000, 100, True)
    assert reservation["reserved_micros"] == 1200
    assert store.status("run-1")["budgets"]["spend_cents"]["consumed"] == 1
    controller.mark_dispatched("paid")
    assert controller.reconcile("paid", attestor.attest("paid", "remote-paid", "vendor/pro-2.1", "provider-2", Usage(900, 90, 100, 0))) == 990


def test_forged_binding_denied(tmp_path):
    _, _, _, controller, binding = setup(tmp_path)
    forged = RunBinding(binding.run_id, binding.task_fingerprint, binding.nonce, "0" * 64)
    with pytest.raises(CostDenied, match="untrusted"):
        controller.begin(forged, "req", "local.code.v1", 1, 1)


def test_wrong_task_binding_denied(tmp_path):
    store, binder, _, _, _ = setup(tmp_path)
    with pytest.raises(CostDenied):
        binder.bind(store, "run-1", "different-task")


@pytest.mark.parametrize("usage", [Usage(-1, 0), Usage(0, -1), Usage(1, 0, 2), Usage(2**63, 0)])
def test_invalid_usage_denied(tmp_path, usage):
    _, _, attestor, controller, binding = setup(tmp_path)
    controller.begin(binding, "req", "local.code.v1", 10, 10)
    controller.mark_dispatched("req")
    with pytest.raises(Exception):
        controller.reconcile("req", attestor.attest("req", "local", "local/code-1.0", "p", usage))


def test_missing_usage_fails_closed_and_survives_restart(tmp_path):
    store, binder, attestor, controller, binding = setup(tmp_path, 10)
    controller.begin(binding, "paid", "remote.paid.v1", 1000, 100, True)
    controller.mark_dispatched("paid")
    with pytest.raises(CostDenied, match="missing"):
        controller.reconcile("paid", None)
    restarted = CostController(tmp_path / "usage.sqlite3", store, models(), binder, attestor, now=lambda: 1001)
    assert restarted.status("paid")["state"] == "AMBIGUOUS"
    with pytest.raises(CostDenied, match="fail closed"):
        restarted.begin(binding, "paid-2", "remote.paid.v1", 1, 1, True)


def test_provider_model_drift_fails_closed(tmp_path):
    _, _, attestor, controller, binding = setup(tmp_path)
    controller.begin(binding, "req", "local.code.v1", 10, 10)
    controller.mark_dispatched("req")
    with pytest.raises(CostDenied, match="identity drift"):
        controller.reconcile("req", attestor.attest("req", "local", "vendor/different", "p", Usage(1, 1)))


def test_crash_before_dispatch_does_not_refund(tmp_path):
    store, _, _, controller, binding = setup(tmp_path, 10)
    controller.begin(binding, "req", "remote.paid.v1", 1000, 100, True)
    controller.abort_before_dispatch("req")
    assert store.status("run-1")["budgets"]["spend_cents"]["consumed"] == 1
    assert controller.status("req")["state"] == "ABORTED"


def test_concurrent_request_identity_prevents_double_reservation(tmp_path):
    store, _, _, controller, binding = setup(tmp_path, 10)
    controller.begin(binding, "same", "remote.paid.v1", 1000, 100, True)
    with pytest.raises(CostDenied, match="duplicate"):
        controller.begin(binding, "same", "remote.paid.v1", 1000, 100, True)
    assert store.status("run-1")["budgets"]["spend_cents"]["consumed"] == 1


def test_direct_ledger_tamper_detected(tmp_path):
    _, _, _, controller, binding = setup(tmp_path)
    controller.begin(binding, "req", "local.code.v1", 1, 1)
    with sqlite3.connect(tmp_path / "usage.sqlite3") as db:
        db.execute("UPDATE events SET payload_json='{}' WHERE seq=1")
    assert not controller.verify_ledger()


def test_true_concurrent_reservation_cannot_double_spend(tmp_path):
    store, _, _, controller, binding = setup(tmp_path, 1)
    barrier = threading.Barrier(3)
    outcomes = []
    def attempt():
        barrier.wait()
        try:
            controller.begin(binding, "race", "remote.paid.v1", 1000, 100, True)
            outcomes.append("reserved")
        except Exception:
            outcomes.append("blocked")
    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join()
    assert sorted(outcomes) == ["blocked", "reserved"]
    assert store.status("run-1")["budgets"]["spend_cents"]["consumed"] == 1
