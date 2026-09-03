# CP11 Run Budgets and AutoWork Protocol

CP11 uses a repository-side bounded controller and a transactional SQLite budget store. Authoritative dimensions are tool calls, mutation calls, network calls, external-effect actions, recovery attempts, candidate rebuilds, wall-clock seconds, child runs, and integer spend cents. Default spend is zero.

Reservations are durable, monotonic, made before execution, and never refunded for failure or crash. Child consumption is charged through its ancestor chain. The durable history is append-only and hash-chained. Terminal and control states fail closed.

AutoWork is finite and checks run/global state, identity/parent envelopes, the existing three-attempt retry threshold, spend, external effect, Safety, and Approval before every action. CP10 retry history is never reset or restored backward.

## Integration decision

`BUDGET_GUARD_MODE=REPO_SIDE`. Hermes pre-tool and pre-API hooks expose authoritative call metadata but no trusted AutoWork run ID binding. Kanban exposes a run ID only on a separate lifecycle observer path. Trusting arbitrary arguments or inventing an unsafe join is prohibited. Trusted runtime binding, model turns, and tokens are `DEFERRED_TO_CP13_COST_CONTROLLER`.
