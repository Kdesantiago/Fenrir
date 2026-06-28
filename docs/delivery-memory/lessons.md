# Lessons

Recurring review / red-team findings worth feeding back into checks.

## 2026-06-28 — A feature cut must SUBTRACT existing behavior before writing acceptance criteria
- **Finding:** the v1 `dashboard-ux-evolve` cut listed acceptance criteria that *already
  passed on main* — kanban cost badge (`app.js:717-726`), epic/assignee filters
  (`index.html:196`), Escape+focus-trap (`app.js:796-804`), column labels, readable
  timestamps. ~Half the cut was a no-op re-implementation. Caught by `red-team-destroyer`
  (VERDICT: REDESIGN) only because it read the actual code, not the spec.
- **Class:** scope inflation from un-audited acceptance criteria — the spec described the
  desired end-state, not the *net-new delta* from current behavior.
- **Check / gate change:** in `challenge-me` Gear-2 (and any UX/feature spec), before
  writing acceptance criteria, grep the codebase for each criterion's current state and
  list a "What already exists — SUBTRACT" section. A cut is net-new or it isn't a cut.
- **Also surfaced:** a "riskiest assumption" (backend already date-filters) was written but
  not verified at spec time; it was FALSE. Lesson: verify the load-bearing assumption with
  code (`file:line`) *during* Gear-2, not deferred to delivery.
