# Owner Ops Runtime Binding

The local dashboard and Discord renderer share the same OwnerOpsReadModel.

Local UI:
- command: python -m owner_ops serve
- default bind: 127.0.0.1:8765
- initial live mode is read-only
- typed controls remain disabled until a trusted inbound identity path exists

Discord:
- initial live binding is outbound single-message webhook only
- secret source is Owner environment variable DARWIN_DISCORD_WEBHOOK_URL
- the secret is never stored in the repository, runtime state, logs, or evidence
- candidate tests use fake openers and make zero real Discord calls
- python -m owner_ops discord-once creates or edits the existing panel

The outbound webhook does not grant approval/control authority.
Inbound Discord controls remain deferred until an authenticated interaction binding is built.
