# VERIFY — realtime-transport

Run after `realtime-transport` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] connection auth is validated AT THE HANDSHAKE — no unauthenticated upgrade path: `grep -RniE "token|authorize|authenticate" <channel-file>` shows a check before the connection is accepted, not only after the first message
- [ ] heartbeat + client reconnect/resume is implemented: server sends ping/keepalive with an idle timeout, and the client reconnects with resume (`Last-Event-ID` for SSE, a resume token for WebSocket)
- [ ] a per-connection backpressure policy is defined: a bounded send buffer with an explicit drop/coalesce rule for slow consumers (no unbounded queue)
- [ ] multi-instance fan-out uses a backplane (Azure SignalR / Web PubSub) — OR the single-instance limitation is stated explicitly in code/docs
- [ ] transport choice (SSE vs WebSocket) is justified for the use case (one-way → SSE; bidirectional → WebSocket)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v az` (for SignalR / Web PubSub provisioning) — note absent, don't fail
- [ ] the SignalR / Web PubSub SDK (or framework realtime extra) is declared in deps
- [ ] an active-connection gauge + disconnect-rate metric are wired (via `observability-gen`)

## Functional
Open a connection and confirm server→client updates arrive. Kill the connection mid-stream and
confirm the client reconnects and **resumes** without losing or duplicating state. Run two server
instances behind the backplane and confirm a message published on instance A reaches a client
connected to instance B. Finally, attempt an unauthenticated upgrade and confirm it is rejected.
