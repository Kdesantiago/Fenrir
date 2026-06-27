---
name: frontend-gen
description: Use when you need framework-aware frontend generation OR convention/a11y checking for react/vue/svelte/streamlit/html. NOT for backend code, APIs, or infra. Reads org-profile.yaml front and refuses on unknown/none framework.
---

# Frontend Generator

## When to use
- "scaffold a component/page" or "check conventions/accessibility" for the declared `front` framework
- Generator mode: produce framework-idiomatic components/pages
- Checker mode: audit existing frontend code against conventions + a11y rules

## When NOT to use
- Backend services, APIs, data layers → use the relevant backend/framework generator
- Infra/deploy → use `iac-gen`
- `front` is unset or unrecognized → this skill refuses

## Inputs
- `org-profile.yaml` → `front` (react | vue | svelte | streamlit | html) — REQUIRED

## Steps
1. Read `org-profile.yaml`; resolve `front`. If unset or not in {react, vue, svelte, streamlit, html}, REFUSE.
   - **`html` = plain static** — no framework/build step: emit semantic HTML + vanilla CSS/JS (progressive enhancement), no React/bundler. a11y rules still apply.
2. Choose mode: GENERATE (new component/page) or CHECK (audit existing frontend).
3. Generate mode: emit framework-idiomatic code following the framework's conventions and project structure.
4. Check mode: audit against framework conventions and accessibility (semantic HTML, ARIA, keyboard nav, contrast).
5. Report results with file:line for any convention/a11y findings.

## Output / validation
- Generated framework-idiomatic components/pages, OR a convention + a11y findings report
- Verify generated code builds/renders in the declared framework; a11y findings map to real elements
- All output is specific to the declared `front`; never emit cross-framework code

## Refuses when
- `front` is unset, `none`, or not one of react/vue/svelte/streamlit/html
- Asked to produce backend logic (out of scope)
