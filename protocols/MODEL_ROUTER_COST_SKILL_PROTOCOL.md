# DARWIN ZERO-0 Model Router, Cost Controller, Cache, and Skill Protocol

## Authority and boundary

CP13 is a repository-side deterministic control boundary. Model-generated text is never authority for model identity, price, spend permission, run identity, usage, Skill trust, or activation. The canonical Integration Registry remains default deny: discovery and download are inputs, not acceptance evidence.

Hermes exposes `pre_api_request` and `post_api_request` hooks with provider/model/request identifiers and provider-normalized usage. This is useful authoritative usage evidence. It is not a complete enforcement boundary: the effective Hermes task ID is caller supplied or randomly created, and API hook errors are swallowed. Therefore CP13 does not claim generic live Hermes run binding. Calls made through the CP13 controller receive an opaque trusted binding created from the CP11 run store; usage there is run-bound and exact. Direct Hermes/provider paths remain outside the candidate enforcement boundary and are reported as `RUN_BOUND_USAGE=LIMITED` until a fail-closed trusted runtime binding is promoted.

## Routing and cost

Accepted immutable model identities are filtered by required capability, risk/privacy policy, context/output capacity, health, Owner permission, known price, and remaining CP11 budget. Known zero-cost routes are preferred only after capability and policy checks. Unknown price is never free. Every fallback is routed again through the same gates. A transition from zero cost to paid requires fresh Owner authorization.

Money uses integer micros; CP11 spend reservation uses conservatively rounded-up integer cents. Paid calls reserve before dispatch. Provider-reported usage reconciles after response. Missing usage, model identity drift, or usage beyond reservation fails closed. Reservations are not refunded after failure or ambiguity. No paid provider calls are used in candidate tests.

## Prompt cache

The local cache is disposable derived state. Keys bind exact model identity, policy, tool schema, CP12 context packet, task fingerprint, content component, retrieval version, trust level, and schema. Secrets, raw environment values, credentials, approvals, permission grants, and budget expansions are not cacheable. Cached text is never a source of truth.

## Skills, MCP, and plugins

Third-party integrations begin as candidates. Immutable provenance, static security scan, isolated dynamic result, security result, effectiveness benchmark, cost analysis, conflict analysis, Acceptance evidence, and Owner authorization are required before activation. Duplicate tools or hooks quarantine deterministically; load order never resolves a security conflict. Skills cannot override Safety, Approval, budgets, continuity authority, Recovery, Constitution, or Owner control. Ruflo remains uninstalled and inactive; it may only be evaluated later as an orchestrator candidate.

## Runtime audit matrix

| Surface | Evidence | CP13 use |
|---|---|---|
| Hermes provider transports | normalized response `Usage` and exact response model | authoritative usage evidence where present |
| `post_api_request` hook | request/task/session/model/provider plus normalized usage | observable, not a blocking boundary |
| `pre_api_request` hook | exact outbound identity and request metadata | observable; exceptions are swallowed |
| Hermes `task_id` | caller supplied or UUID fallback | not trusted as CP11 run ID |
| Hermes fallback chain | automatic provider fallback exists | CP13 route boundary revalidates every fallback |
| CP11 BudgetStore | transactional run identity and spend cents | trusted reservation envelope |
| CP12 ContinuityEngine | bounded provenance-backed packets | cache/router input, never price/permission authority |
| Integration Registry v2 | default deny, registry required | extended, not bypassed |

## Modes

- `MODEL_ROUTER_MODE=REPO_SIDE_DETERMINISTIC`
- `COST_CONTROLLER_MODE=RUN_BOUND_ACCOUNTING_LIMITED_TO_CONTROLLED_BOUNDARY`
- `PROMPT_CACHE_MODE=LOCAL_HASH_BOUND`
- `SKILL_REGISTRY_MODE=DEFAULT_DENY_EVALUATED`
