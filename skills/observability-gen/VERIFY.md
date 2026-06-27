# VERIFY — observability-gen

Run after `observability-gen` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] OpenTelemetry SDK init exists for the declared `framework` (tracer/meter/logger providers + resource attributes) in the generated module
- [ ] async resilience patterns emitted: timeout wrappers, retry-with-backoff, and backpressure/bounded concurrency are all present
- [ ] exporter is ENV/config-driven, NEVER hardcoded — `! grep -rEi '(otlp|endpoint|api[_-]?key)\s*[:=]\s*["'\'']https?://[^"'\'' ]+' <generated-dir>` (OTLP endpoint/headers come from ENV)
- [ ] matches `org-profile.yaml`: when `obs_backend: langfuse`, LLM tracing is wired over OTLP/SDK (prompt/model/tokens/latency/cost) and host+keys come from ENV — not hardcoded

## Informational (tooling presence — does NOT block; note if absent)
- [ ] the OTel SDK + framework instrumentation packages installed; a local OTLP collector available for the export check → note absent, don't fail

## Functional
- Run the app against a local OTLP collector: spans/metrics export and the resource attributes populate. Switching `obs_backend` requires only ENV/config changes (no code edits) — confirm by grep that the backend name isn't baked into source.
