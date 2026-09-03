from dataclasses import dataclass
from .budget_store import BudgetDenied

@dataclass(frozen=True)
class Action:
    name: str
    mutation: bool = False
    network: bool = False
    external_effect: bool = False
    spend_cents: int = 0
    recovery: bool = False
    candidate_rebuild: bool = False

class AutoWorkController:
    """Finite controller whose caller must supply an explicit iteration bound."""
    def __init__(self, store, run_id, retry_probe, safety_probe, approval_probe):
        self.store, self.run_id = store, run_id
        self.retry_probe, self.safety_probe, self.approval_probe = retry_probe, safety_probe, approval_probe

    def amounts(self, action):
        result = {"tool_calls_total": 1}
        if action.mutation: result["mutation_tool_calls"] = 1
        if action.network: result["network_tool_calls"] = 1
        if action.external_effect: result["external_effect_actions"] = 1
        if action.spend_cents: result["spend_cents"] = action.spend_cents
        if action.recovery: result["recovery_attempts"] = 1
        if action.candidate_rebuild: result["candidate_rebuilds"] = 1
        return result

    def execute(self, actions, executor, max_iterations):
        if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 0:
            raise BudgetDenied("invalid finite bound")
        output = []
        for index, action in enumerate(actions):
            if index >= max_iterations: break
            status = self.store.status(self.run_id)
            if status["state"] != "RUNNING" or status["frozen"]: raise BudgetDenied("run unavailable")
            if self.retry_probe() >= 3: raise BudgetDenied("Execution Discipline threshold")
            if action.spend_cents > 0 and not self.approval_probe("spend", action): raise BudgetDenied("OWNER_DECISION")
            if action.external_effect and not self.approval_probe("external_effect", action): raise BudgetDenied("external effect denied")
            if not self.safety_probe(action): raise BudgetDenied("Safety boundary")
            self.store.reserve(self.run_id, self.amounts(action))
            success = False
            try:
                value = executor(action); success = True; output.append(value)
            finally:
                self.store.record_result(self.run_id, success)
        return output
