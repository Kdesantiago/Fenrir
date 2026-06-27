# Delivery Skillset — Standard de livraison org-portable (v2)

> v2 = v1 corrigée après red-team. 5 kill shots traités. Lire `## Kill shots → fixes` d'abord.

## Principe central (le fix #1, le plus important)

**Une skill ne peut PAS enforcer.** C'est du texte advisory que le modèle *choisit* de suivre. Le vrai gate vit dans l'INFRA déterministe: git hooks + CI required-checks + branch-protection-as-code. Les skills = **feedback rapide local**, pas la barrière.

Donc le standard de livraison = **3 produits distincts**, pas 1 skillset:

| Module | Quoi | Primitive | Owner |
|---|---|---|---|
| **A. INFRA (couche 0)** | repo-template + hooks + CI + branch-protection. **Le vrai gate.** | Fichiers déterministes, pas modèle | Platform team |
| **B. GENERATORS** | scaffold profile-driven (iac/auth/obs/front/llm) | Skills lisant `org-profile.yaml` | Platform team |
| **C. ORCHESTRATION** | subagents + `/deliver` + `/ship` | Subagents + commands | DevEx |

Tout livré en **1 plugin Claude Code versionné (semver)**, pas de copie `~/.claude` par repo (= drift garanti).

---

## Couche 0 — INFRA (le vrai standard, surtout PAS des skills)

C'est ici que "standardiser la livraison" a des dents. Déterministe, hors discrétion du modèle.

| Composant | Mécanisme | Enforce quoi |
|---|---|---|
| `pre-commit` / `pre-push` hooks | git hooks (installés par `repo-bootstrap`) | lint, type, secret-scan, format — local, avant push |
| CI required status checks | pipeline (Azure/GH Actions) | test, coverage, SAST, build — bloque merge |
| branch-protection-as-code | Terraform/GH API/Azure policy | PR obligatoire, checks requis, CODEOWNERS review |
| repo-template versionné | template repo / cookiecutter | structure org, assertion version |

**Protocole**: `repo-bootstrap` génère ces fichiers + applique branch-protection via IaC. La skill installe; l'INFRA enforce.

---

## org-profile.yaml (le fix #2 — sans ça, les generators crachent du code hors-stack)

Les generators ne sont PAS portables nus (OIDC≠SAML, k8s≠serverless, React≠Streamlit). Ils lisent un profil et **refusent si mismatch**.

```yaml
# org-profile.yaml — racine du repo
platform: aks          # aks | webapp | k8s | serverless | vm | ecs
framework: fastapi     # fastapi | express | spring | streamlit
auth_provider: entra   # entra | okta | keycloak | auth0
obs_backend: grafana   # grafana | datadog | cloudwatch | honeycomb | langfuse
llm_provider: anthropic # anthropic | openai | azure | bedrock | vertex
front: streamlit       # react | vue | svelte | streamlit | html | none
```

Generator sans profil correspondant → **hard stop, message clair**. Pas de scaffold deviné.

---

## Couche 1 — SKILLS (`~/.claude/skills/<nom>/SKILL.md` via plugin)

Trimmées vs v1: overlaps tués, secret-scan retiré (→ hook), ADR retiré de doc (→ architect).

| Skill | Job | Trigger (description front-loadée) | Note fix |
|---|---|---|---|
| `repo-bootstrap` | Init repo NEUF: structure, hooks, CI skeleton, branch-protection IaC, renovate, CODEOWNERS. **Idempotent, skip si existe.** | "initialize a NEW repo tooling — NOT for running checks" | Seul propriétaire du CI skeleton (fix collision §1) |
| `delivery-gates` | Lance lint+type+test+coverage **localement** = feedback rapide. **Advisory.** Vrai gate = couche 0. | "run existing checks on a diff for fast local feedback" | N'enforce pas; le dit explicitement (fix #1) |
| `security-review` | Wrap `/security-review` natif: SAST + SBOM + threat-check sur diff. **Pas de secret-scan** (→ hook). | "SAST/SBOM/threat on a diff" | Secret-scan = 1 seul endroit (fix §1) |
| `doc-generator` | Agrège/formate docs existantes: README, API docs, changelog. **Pas d'ADR.** | "aggregate & format existing docs" | ADR appartient à `architect` (fix §1) |
| `iac-gen` | Generator profile-driven: Helm/ArgoCD si `platform=k8s`, sinon refuse | "generate IaC for the declared platform" | Lit profil, refuse mismatch (fix #2) |
| `auth-gen` | Generator: OIDC/OAuth2 selon `auth_provider`. **Jamais d'auth auto non-revue.** | "generate auth glue for declared provider" | Refuse sans profil; auth = revue humaine obligatoire (fix #2, sécu) |
| `observability-gen` | OTel SDK init + semantic conventions; backend via env, jamais hardcodé | "generate vendor-neutral OTel init" | Backend = config (fix #2) |
| `frontend-gen` | Generator OU convention-checker selon `front`; a11y rules framework-aware | "scaffold/check front for declared framework" | Refuse si framework inconnu (fix #2) |
| `llm-gen` | Wrapper typé pour `llm_provider`; golden-set eval, cost tracking | "generate LLM wrapper for declared provider" | 1 provider/profil; SDK à vérifier docs (fix #2) |

---

## Couche 2 — SUBAGENTS (`~/.claude/agents/<nom>.md`)

Trimmés vs v1 (fix §7 — overlap natif).

| Subagent | Verdict | Job |
|---|---|---|
| `architect` | **GARDE** — distinct, read+plan, tools restreints | Design, **ADR (décide+écrit)**, trade-offs |
| `qa-tester` | **GARDE** — tool-profile distinct | Écrit NOUVEAUX tests + reproduit bugs (≠ gates qui exécutent l'existant) |
| `reviewer` | **WRAP natif** — pas de persona custom | Appelle `/code-review` natif + règles PR-hygiene org-spécifiques uniquement |
| `coder` | **KILL** sauf besoin toolset restreint | Sinon = comportement par défaut du main thread |

---

## Couche 3 — ORCHESTRATION (le "Chef de projet", fix §4)

| Command | Job | Fixes appliqués |
|---|---|---|
| `/deliver` | Pipeline: architect→coder→qa→reviewer→gates→PR | (a) **spec-artifact sur disque** = source de vérité que chaque subagent relit (anti context-loss). (b) **routing déterministe par script** (LOC, fichiers risque via globs), pas jugement LLM. (c) **checkpoint git par stage** + resume. (d) gates réels = CI, pas la command. |
| `/ship` | Ouvre PR + affiche statut CI | **Ne prétend PAS enforcer** — branch-protection (infra) bloque le merge, pas `/ship` (fix #1) |

**Adaptatif résolu**: script calcule taille/risque → route `light` (hotfix) vs `full` (feature). Déterministe, reproductible.

---

## Distribution (fix #4 — anti-drift)

- **1 plugin Claude Code, semver, 1 repo of record, changelog, owning team.**
- Repos consomment une **version pinnée**. Update = bump du pin. Copie `~/.claude` interdite.
- `delivery-gates` **assert la version du repo-template**, fail loud si mismatch.

---

## Primitives ajoutées (fix §6 — manquaient)

Rangées par priorité:

1. **Enforcement infra** (hooks + CI required-checks + branch-protection-as-code) — *déjà couche 0*
2. **Release mgmt**: semver, tags, changelog auto, release notes
3. **Supply-chain**: SLSA/provenance, artifact signing, deps pinnées, license-policy enforce
4. **Secrets mgmt** (vault/SOPS) — ≠ secret *scanning*
5. **Env promotion + rollback + data-migrations** — la livraison ne s'arrête pas à la PR
6. **Dependency policy**: règles merge/pin Renovate, pas juste le fichier
7. **ADR-required CI check** sur diffs architecturaux (≠ générer un ADR)

---

## Kill shots → fixes (résumé)

| # | Kill shot v1 | Fix v2 |
|---|---|---|
| 1 | Skill ne peut pas enforcer le gate | Gate → couche 0 INFRA (hooks+CI+branch-protection). Skill = advisory |
| 2 | 5 scaffolds non-portables | `org-profile.yaml` + generators qui refusent sur mismatch |
| 3 | `/deliver` multi-agent fragile | spec-artifact disque + routing script déterministe + checkpoints |
| 4 | Distribution = drift | 1 plugin semver pinné, owning team |
| 5 | 3 produits en 1 | Split A(infra)/B(generators)/C(orchestration). **Ship A en premier** |

---

## Ordre de mise en place (recommandé)

1. **Couche 0 INFRA** + `repo-bootstrap` — sans ça, rien n'enforce. C'est le mandat réel.
2. `org-profile.yaml` + 1 generator pilote (`iac-gen` sur stack k8s actuelle)
3. `delivery-gates` + `security-review` (wrap natif)
4. Subagents `architect` + `qa-tester`
5. `/deliver` + `/ship`
6. Release + supply-chain + secrets (primitives ajoutées)
