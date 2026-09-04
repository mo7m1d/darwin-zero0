# DARWIN ZERO-0 Owner Operations Protocol

Owner Ops is a presentation and typed-control client over existing durable control-plane sources.
Discord and the local UI are not canonical truth and must not become shadow databases.

Primary panel updates are event-driven and burst-coalesced. The minimum edit interval is 3-10 seconds.
A heartbeat may occur at 60 seconds or slower. Rendering and heartbeat do not invoke an LLM.

Discord/local control flow is:
exact Owner/guild/channel identity -> nonce/expiry/replay validation ->
narrow typed control request -> existing CP11/Approval/Recovery/Model-control path -> durable evidence.

There is no arbitrary shell endpoint. The local UI binds to 127.0.0.1 by default.
Candidate tests use a fake Discord transport and perform no Discord network call.
Secret-like snapshot material is redacted.
