# Self-Healing Protocol

1. Detect error or degraded health.
2. Capture logs and error signature.
3. Search incident memory for prior successful fixes.
4. Diagnose likely root cause.
5. Research official documentation/web if uncertain.
6. Create a patch candidate in an isolated workspace.
7. Run targeted tests, regression tests, and health checks.
8. If successful, deploy through controlled promotion.
9. If unsuccessful, rollback and try an alternative hypothesis.
10. Escalate only when repeated safe attempts fail or the incident touches money, secrets, security boundaries, irreversible data loss, or owner controls.
11. Save successful reusable fixes as incident knowledge and, when appropriate, a Hermes skill.
