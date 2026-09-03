# Recovery & Checkpoint Protocol

CP10 provides integrity-first recovery for mutable DARWIN runtime state.

1. Source code recovery remains Git-backed; runtime checkpoints must not become shadow source control.
2. Checkpoint sources are explicit allowlisted runtime-state roots only.
3. Secret-like paths, credentials, `.env*`, SSH material, directories, symlink traversals, oversized files, and paths outside allowlisted roots are rejected.
4. Every checkpoint is immutable, content-hashed, recorded in a hash-chained checkpoint ledger, and carries provenance plus evidence references.
5. Restore is never a blind overwrite. A restore plan verifies checkpoint integrity and requires an expected-current hash for every destination.
6. Actual restore requires explicit Owner authorization and uses temporary sibling files plus atomic replacement.
7. Recovery knowledge is data-only. External observations can create candidate knowledge but cannot become trusted automatically.
8. Trusted recovery knowledge requires a PASS from the Acceptance Gate with an `acceptance:` evidence reference.
9. Recovery knowledge must never directly execute code, shell commands, remote content, plugins, Skills, or packages.
10. After three failed attempts on the same unresolved root cause, Execution Discipline remains authoritative and mutation stops pending escalation.

Recovery evidence is not a substitute for runtime acceptance evidence.
