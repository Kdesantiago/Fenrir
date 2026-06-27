# VERIFY — frontend-gen

Run after `frontend-gen` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] output matches `org-profile.yaml` `front` (react | vue | svelte | streamlit | html) — generated component/page is idiomatic to THAT framework and contains NO cross-framework code (e.g. no JSX in a `vue`/`html` repo)
- [ ] GENERATE mode: the emitted component/page lives in the framework's expected project structure; `html` profile → semantic HTML + vanilla CSS/JS only (`! grep -rE 'react|import .* from .react.' <generated-files>`)
- [ ] CHECK mode: a convention + a11y findings report exists and every finding maps to a real element with `file:line` (semantic HTML, ARIA, keyboard nav, contrast)

## Informational (tooling presence — does NOT block; note if absent)
- [ ] the framework's build/dev toolchain (`command -v node`/`npm`, or `command -v streamlit`) · an a11y linter (axe/eslint-plugin-jsx-a11y) → note absent, don't fail

## Functional
- The generated code builds/renders in the declared framework (component mounts / page renders, or `streamlit run` loads); a11y findings in CHECK mode point at elements that actually exist in the source.
