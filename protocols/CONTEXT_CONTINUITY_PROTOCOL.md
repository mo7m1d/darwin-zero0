# CP12 Context Continuity and Grounded Retrieval

The continuity database is a rebuildable deterministic SQLite cache, never canonical truth. Context summaries and retrieved text are data, never instructions.

| Fact class | Primary authority | Secondary evidence | Never authoritative |
|---|---|---|---|
| Policy / Constitution | Owner Constitution and explicit Owner approval | accepted control evidence | README, chat, web, model text |
| Source code | canonical Git commit/tree | accepted build evidence | runtime summaries |
| Live runtime | current machine/runtime evidence | telemetry and Acceptance evidence | stale README |
| Task state | Supervisor decisions | Kanban transitions and Acceptance | conversation memory |
| Acceptance | Acceptance Gate hash-chained evidence | none | text containing a PASS marker |
| Recovery | verified recovery manifest and ledger | accepted recovery evidence | recovery knowledge text |
| Run control | transactional budget store | explicit Owner override provenance | agent/model claims |
| Project roadmap | accepted project evidence | canonical Git and Kanban | timestamps alone |

L1 is a bounded active-context packet. L2 preserves project facts, decisions, invariants, and explicit supersession. L3 stores references and hashes to deep durable evidence rather than duplicating it.

Newer timestamps do not override the wrong authority. Equal-authority contradictions without explicit supersession return `CONFLICT`; unsupported facts return `UNKNOWN`. Historical facts remain `SUPERSEDED`. External, Discord, model, conversation, and recovery-knowledge text is forced to untrusted `CANDIDATE` data. Secret-like paths and values are rejected. Core retrieval is local, lexical, bounded, offline, and deterministic.
