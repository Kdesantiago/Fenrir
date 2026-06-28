# VERIFY — event-driven

Run after `event-driven` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] the primitive matches the declared `platform` and the choice is justified (Service Bus → commands/queues; Event Grid → reactive events; Event Hubs → streams); the producer/consumer file exists: `git grep -lEi 'servicebus|eventgrid|eventhub' -- '*.py' && echo OK || echo MISSING`
- [ ] the message/event has a **versioned** schema wrapped in a CloudEvents-style envelope (`id`/`source`/`type`/`specversion`/`data`), validated on produce AND consume: `git grep -nEi 'specversion|cloudevent|schema_version|event_version' && echo OK || echo MISSING`
- [ ] the consumer is **idempotent** — a dedup-by-message-id / idempotency-key strategy is stated and implemented: `git grep -nEi 'idempoten|dedup|duplicate.detection|message_id|already_processed' && echo OK || echo MISSING`
- [ ] a **dead-letter path + bounded poison-message handler** exists (no infinite redelivery): `git grep -nEi 'dead.?letter|deadletter|\$DeadLetterQueue|max.?delivery|poison|max_attempts' && echo OK || echo MISSING`
- [ ] auth is **managed identity** (`DefaultAzureCredential` against the namespace FQDN), no literal connection string / SAS key: `! git grep -nEi 'Endpoint=sb://|SharedAccessKey=|AccountKey=' && echo OK || echo LITERAL-SECRET`
- [ ] DLQ-depth + consumer-lag **alerting** is wired via `obs_backend` and a trace correlation id is propagated through the envelope

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v az` · `python -c 'import azure.servicebus' 2>/dev/null` · `python -c 'import azure.eventgrid' 2>/dev/null` · `python -c 'import azure.eventhub' 2>/dev/null` · `python -c 'import azure.identity' 2>/dev/null` → note absent, don't fail

## Functional
- Against a real (or emulated) bus: publish a message and confirm the consumer processes it; redeliver the SAME message id and confirm the second delivery is a no-op (dedup proven); force a poison message (bad schema / always-failing handler) and confirm it lands in the DLQ after the bounded retry count rather than redelivering forever; confirm the DLQ-depth metric increments and the configured alert would fire.
