---
name: realtime-transport
description: Use when building a server-push / realtime channel — WebSocket or SSE for live updates, token streaming, or notifications — with the reconnect/backpressure/auth discipline a naive socket lacks. Triggers — "push updates to the client", "WebSocket", "server-sent events / SSE", "stream tokens to the UI", "live notifications feed". NOT for request/response HTTP (use `api-first`), NOT for backend message buses (use `event-driven`), NOT for scheduled push (use `cronjob`). Reads org-profile.yaml `framework`/`front` and refuses on mismatch.
---

# Realtime Transport — server push done safely

A naive `while True: socket.send(...)` works in a demo and falls over in prod: unauthenticated
upgrades, no reconnect, unbounded buffers, and dead in-memory state the moment you run two
instances. This skill scaffolds the **discipline** around server push. It writes the channel; the
*operational* guarantees (a backplane actually provisioned, metrics actually scraped) are real
infra the skill can only set up, not enforce.

## When to use
- "push live updates to the browser/client", "stream LLM tokens to the UI"
- "add a WebSocket / SSE endpoint", "real-time notifications feed"

## When NOT to use
- Request/response HTTP endpoints → `api-first` (it scopes out non-HTTP transport)
- Backend queue/topic/event streams (service-to-service) → `event-driven`
- Scheduled / periodic push → `cronjob`
- No declared `framework`/`front` → this skill refuses

## Inputs
- `org-profile.yaml` → `framework` (server transport idioms) + `front` (client reconnect code) — REQUIRED
- `auth_provider` → token validation at the handshake (cross-ref `auth-gen`)
- `platform` → the scale-out backplane target (Azure SignalR / Web PubSub)

## Steps
1. **Pick the transport.** SSE for one-way server→client push (simpler, plain HTTP, auto-reconnect); WebSocket for bidirectional. Justify the choice — don't default to WebSocket.
2. **Auth at the handshake.** Validate the token on connect/upgrade (not on the first message); reject unauthenticated upgrades. Reuse `auth-gen` glue.
3. **Liveness.** Heartbeat/ping + idle timeout; client reconnect with **resume** (`Last-Event-ID` for SSE / a resume token for WS) so a dropped connection doesn't lose state.
4. **Backpressure.** Bound the per-connection send buffer; define the drop/coalesce policy when a slow consumer can't keep up. No unbounded queues.
5. **Scale-out.** A backplane (Azure SignalR / Web PubSub) for multi-instance fan-out — in-memory pub/sub only works single-instance; if you stay in-memory, state that limit explicitly.
6. **Observability.** Wire an active-connection gauge, disconnect-rate, and message-lag metrics via `observability-gen`.

## Output / validation
A channel endpoint (server) + client connect/reconnect code, with handshake auth, heartbeat,
bounded buffers, and either a backplane or a documented single-instance limit. Validate with
`VERIFY.md`: open a connection, push updates, kill it mid-stream and confirm reconnect+resume,
and run two server instances to confirm fan-out reaches a client on the other instance. The
skill sets these up; the channel is only as reliable as the backplane + metrics actually deployed.

## Refuses when
- `framework` or `front` is unset/unknown in `org-profile.yaml`.
- The request is request/response HTTP (→ `api-first`), a backend bus (→ `event-driven`), or scheduled push (→ `cronjob`).
- Asked to ship an unauthenticated upgrade or an unbounded send buffer.
