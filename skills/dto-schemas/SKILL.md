---
name: dto-schemas
description: >-
  Use when authoring/fixing pydantic v2 in/out DTOs in the `schemas/` layer — typed
  fields with declarative constraints, separate request/response models (no
  over-posting, no over-exposure), strict parsing, lossless serialization. Triggers —
  "add a request/response model", "validate this input", "the DTO for X", "fix the
  serialization", "reject unknown fields". NOT for the ORM/persistence model (→
  data-access-coder), NOT for the OpenAPI path/operation (→ api-coder owns the
  contract; this owns the `components/schemas` shapes feeding it), NOT for business
  rules (→ domain-services). Refuses-when org-profile `framework` mismatch/unset |
  asked to design (→ architect) | asked to gate/merge (→ reviewer) | touches a gate
  file (.claude/, CI).
---

# DTO schemas — the `schemas/` layer (pydantic v2 in/out)

This skill is the implementer for the DTO layer: it authors the pydantic v2 request/response models, validators, and serializers in `src/<module>/schemas/` that api-coder binds and domain-services consumes. It is **advisory** — it writes the declarative shape; the teeth are the VERIFY checks + qa-tester round-trip tests. The core rule: **validation is declarative on the model, and in/out are separate** — a request DTO never accepts a server-controlled field and a response DTO never exposes an internal/secret one. Core behavior is ZERO-cloud: it works with no az/terraform/gh present.

## When to use
- "add a request/response model", "the DTO for X", "validate this input declaratively"
- "fix the serialization" / "round-trip is lossy" / "datetime/Decimal/enum encodes wrong"
- "reject unknown fields on this input" (`extra="forbid"`), "stop over-posting / over-exposing"
- Authoring the `components/schemas` shapes that feed api-coder's contract

## When NOT to use
- The ORM / persistence model, repository, or query → `data-access-coder` (DTOs are not ORM rows)
- The OpenAPI path/operation, status codes, pagination contract → `api-coder` (it owns the contract; this owns the schema shapes it references)
- Business rules / invariants / use-case orchestration → `domain-services` (validators do shape only, never business logic)

## Inputs
- `org-profile.yaml` → `framework` — REQUIRED (FastAPI/pydantic stack). Refuse on mismatch/unset.
- The field set + direction (request vs response) and which fields are **server-controlled** (id, timestamps, role) or **secret/internal** (password hash, internal flags) — this decides in/out separation.
- The constraints per field (lengths, ranges, regex, enum members) and the coercion/alias rules.

## Steps
1. **Read `org-profile.yaml`; resolve `framework`.** If unset or not the supported pydantic-v2 shape, REFUSE — do not author models off-stack. Read sibling `schemas/` files for convention first.
2. **Type every field with explicit constraints.** Pydantic v2 `Field(...)` with `min_length`/`max_length`, `ge`/`le`, `pattern`, enums — validation is **declarative on the model**, never scattered `if` checks in a handler.
3. **Separate in/out models.** Request DTOs omit server-controlled fields (id, created_at, role) so they can't be over-posted; response DTOs omit internal/secret fields (password hashes, internal flags) so they can't be over-exposed. Do not reuse one model for both directions when they differ.
4. **Strict parsing on inputs.** Reject unknown fields with `model_config = ConfigDict(extra="forbid")` where appropriate; make coercion rules explicit (`strict=True` on fields that must not silently coerce). An input that silently swallows unexpected keys is an over-post hole.
5. **Round-trip safety.** Models serialize/deserialize losslessly; `datetime`/`Decimal`/enum encode deterministically; field `alias`/`serialization_alias` handled and `populate_by_name` set when both wire and python names are used.
6. **Validators stay pure.** `@field_validator`/`@model_validator` do shape/constraint checks only — **no I/O, no DB/HTTP, no business rules** (those belong to domain-services). A validator that calls out is the wrong layer.
7. **Prove the narrow path.** Construct a valid instance, a rejected-invalid instance, and a `model_dump_json` → `model_validate_json` round-trip (Bash, in the module venv) to show the model behaves as declared.

## Output / validation
- The pydantic in/out models + validators + serializers in `schemas/`: every field typed-and-constrained, request/response separated, `extra="forbid"` on strict inputs, lossless round-trip, pure validators — plus the one-line construct/reject/round-trip proof.
- Validation: a server-controlled field POSTed into a request DTO is rejected (no over-post); a secret field is absent from the response DTO's `model_dump` (no over-expose); an unknown key is rejected on a `forbid` input; `model_validate_json(model_dump_json(x)) == x` holds for datetime/Decimal/enum. See `VERIFY.md`.
- Boundary: this skill writes the DTO shapes; it does not enforce the API contract (api-coder) or business invariants (domain-services). The teeth are the committed model config + the VERIFY greps + qa-tester's round-trip/over-post tests.

## Optional Azure layer (pointer, not inlined)
None required. DTO schemas are cloud-agnostic by design; this skill never loads or blocks for az/terraform/gh, and ships without any cloud dependency. (A one-line opt-in pointer only applies if `org-profile.yaml cloud_layer: azure` ever attaches one — never inlined, never required.)

## Refuses when
- `org-profile.yaml` missing, or `framework` not the supported pydantic-v2 stack.
- Asked to put business logic or I/O inside a validator (→ domain-services), to model an ORM/persistence entity (→ data-access-coder), or to author the OpenAPI path/operation (→ api-coder).
- Asked to ship one shared model for both request and response when their fields legitimately differ (that is the over-post / over-expose hole this skill exists to close) — split them and say so.
