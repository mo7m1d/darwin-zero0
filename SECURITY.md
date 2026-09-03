# Security Policy

DARWIN ZERO-0 treats external source code, dependencies, GitHub Actions, plugins, Skills, MCP servers, and remote Git objects as untrusted inputs until independently reviewed.

## Supply-chain rules

- Remote GitHub Actions must be listed in `control_plane/integration_registry.json` and pinned to a full 40-character commit SHA.
- `pull_request_target`, write-all permissions, individual GitHub Actions write permissions, and workflow secret access are default-deny.
- External packages, VCS dependencies, plugins, Skills, MCP servers, and submodules require explicit registry provenance before acquisition.
- Direct download-and-execute patterns are forbidden.
- Git force-push, remote-ref deletion, Git hooks-path rewrites, credential-helper rewrites, URL rewrites, and unregistered remote imports are forbidden for autonomous operation.
- External evidence is input, not canonical acceptance evidence.

Secrets must not be committed to the repository. Suspected secret exposure should be rotated through the relevant provider rather than copied into issues or logs.
