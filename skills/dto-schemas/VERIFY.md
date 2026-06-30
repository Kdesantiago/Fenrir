# VERIFY — dto-schemas

Run after `dto-schemas` has been applied to a repo. All BLOCKING checks must pass.

These checks are scoped to the **schemas layer** — the file(s) under a `schemas/` dir (or files defining pydantic `BaseModel`s) — not the whole repo. A repo-wide word search is not falsifiable (a stray `Field(` or `datetime` would pass with zero DTO code). Resolve the schema file(s) first, then run the co-located checks against them:

```
SCHEMA_FILES=$(grep -rlE 'class\s+\w+\(.*\bBaseModel\b|pydantic|ConfigDict' --include='*.py' $(git ls-files '*/schemas/*.py' 2>/dev/null | xargs -n1 dirname 2>/dev/null | sort -u) . 2>/dev/null | sort -u)
echo "${SCHEMA_FILES:-<none — schemas layer not found, FAIL>}"
```
If `SCHEMA_FILES` is empty, the skill produced no pydantic models → FAIL all blocking checks below.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] **pydantic v2 models present** — at least one `BaseModel` subclass in the schema file(s): `for f in $SCHEMA_FILES; do grep -qE 'class\s+\w+\(.*\bBaseModel\b' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-MODEL`
- [ ] **declarative constraints, not scattered ifs** — fields carry explicit constraints via `Field(...)`/annotated types (`min_length`/`max_length`/`ge`/`le`/`pattern`/enum), not `if`-checks in the model: `for f in $SCHEMA_FILES; do grep -qE 'Field\(|min_length|max_length|\bge=|\ble=|pattern=|gt=|lt=|StringConstraints|conint|constr' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-CONSTRAINTS`
- [ ] **strict parsing on inputs** — at least one request/input model forbids unknown fields (`extra="forbid"`), so over-posting is rejected: `for f in $SCHEMA_FILES; do grep -qE 'extra\s*=\s*["'\'']forbid["'\'']' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-EXTRA-FORBID`
- [ ] **in/out separation** — request and response shapes are distinct models, not one reused class (heuristic: ≥2 model classes whose names signal direction): `for f in $SCHEMA_FILES; do grep -hoE 'class\s+\w*(Request|Create|Update|In|Response|Read|Out|Public)\w*\(' "$f"; done | sort -u | wc -l | awk '$1>=2{print "OK"} $1<2{print "REVIEW: confirm request vs response models are separated"}'`
- [ ] **no business logic / I/O in validators** — validators do shape/constraint only; no DB/HTTP/session call inside a `@field_validator`/`@model_validator`: `! grep -rEq '(field_validator|model_validator)[\s\S]{0,400}?(session|requests\.|httpx|\.query\(|\.execute\(|open\(|os\.environ)' $SCHEMA_FILES && echo OK || echo IO-IN-VALIDATOR`
- [ ] **no secret/internal field on a response/out model** (over-expose backstop) — a `Response`/`Read`/`Out`/`Public` model must not declare a secret-ish field: `! for f in $SCHEMA_FILES; do awk '/class .*(Response|Read|Out|Public).*BaseModel/{c=1} c&&/^class /&&!/(Response|Read|Out|Public)/{c=0} c' "$f"; done | grep -qiE 'password|secret|hash|salt|api_?key|token|ssn|private' && echo OK || echo SECRET-FIELD-ON-RESPONSE`
- [ ] (profile-driven) `framework` in `org-profile.yaml` is the supported pydantic-v2 shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `python -c 'import pydantic; assert pydantic.VERSION.startswith("2")'` → pydantic v2 importable (note absent, don't fail)
- [ ] field `alias`/`serialization_alias` + `populate_by_name` present where wire names differ from python names (round-trip hygiene): `grep -rEq 'alias=|serialization_alias=|populate_by_name' $SCHEMA_FILES && echo "alias handling present" || echo "NOTE: no aliases — confirm wire and python names match"`
- [ ] explicit coercion control where it matters (`strict=True`) — note if a field that must not silently coerce lacks it.

## Functional
Construct a VALID instance and confirm it parses; feed an INVALID payload (out-of-range / bad pattern / unknown key on a `forbid` input) and confirm pydantic raises `ValidationError`; POST a server-controlled field (e.g. `id`/`role`) into a request DTO and confirm it is rejected or dropped (no over-post); dump a response DTO and confirm no secret/internal field appears (no over-expose); finally assert `Model.model_validate_json(x.model_dump_json()) == x` for an instance carrying `datetime`/`Decimal`/enum values (lossless round-trip). Run in the module venv: `cd src/<module> && uv run pytest`.
