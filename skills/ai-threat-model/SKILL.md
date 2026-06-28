---
name: ai-threat-model
description: Use when you want a DESIGN-TIME threat model of an LLM/agent system — enumerate the LLM-specific attack surface (prompt-injection direct + indirect, data-exfiltration, tool/function abuse & excessive agency, jailbreak/guardrail-bypass, sensitive-info disclosure, supply-chain, insecure output handling, denial-of-wallet), map each to component + likelihood/impact + a concrete mitigation, write findings to docs/threat-models/. Triggers — "threat model this agent/LLM system", "what can go wrong with this prompt/tool setup", "STRIDE/OWASP-LLM the design". NOT the runtime security-guardrail agent (judges LIVE prompts), NOT security-review (SAST/SBOM on a diff), NOT dat-architect (whole architecture doc). Reads org-profile.yaml `llm_provider`.
---

# AI Threat Model — design-time

Threat-model the **design** of an LLM/agent system before it ships: enumerate the
LLM-specific attack surface, rate each threat, and attach a concrete mitigation, grounded
in the actual repo. This is **analysis, not enforcement** — it produces a document, it does
not gate, scan a diff, or judge a live prompt. The teeth are elsewhere (the runtime
guardrail at request time, CI required-checks at merge time); this is the upstream map that
tells those teeth what to bite.

## When to use
- "threat model this agent / LLM feature / RAG pipeline / tool-calling design"
- Before building or signing off an LLM system that ingests untrusted text, calls tools, or touches secrets/PII
- You want an OWASP-LLM-Top-10-framed enumeration mapped to YOUR components + mitigations

## When NOT to use
- Judging a LIVE user prompt for injection/jailbreak at request time → `security-guardrail` agent (runtime hook), not this
- SAST / dependency / SBOM / threat-check over a git diff → `security-review`
- The whole technical-architecture document (the DAT may LINK this threat model) → `dat-architect`
- Recording a one-off decision/waiver about an accepted risk → `memory-keeper`

## Inputs
- `org-profile.yaml` → `llm_provider` (`anthropic` | `openai` | `azure` | `bedrock` | `vertex` | `none`); if `none`, say there is no LLM surface and stop
- A described system: its prompts/system messages, retrieval/RAG sources, the tools/functions the model may call, what data + secrets it can reach, and where its output flows (rendered HTML, shell, SQL, downstream calls)
- The actual repo — read the agent/prompt/tool code; cite `file:line`. Do not threat-model an imagined system.

## Steps
1. Read `org-profile.yaml`; resolve `llm_provider`. If `none`, report "no LLM/agent surface" and stop.
2. **Map the surface.** From the repo, list: trust boundaries (untrusted text in → model → privileged action out), retrieval sources, every callable tool/function and its blast radius, the secrets/PII the agent can reach, and every sink the model output reaches.
3. **Enumerate threats** across the LLM-specific classes, each tied to a real component (cite `file:line`):
   - **Prompt injection — direct** (user overrides instructions) **and indirect** (malicious instructions in retrieved docs / tool results / web content the model ingests).
   - **Sensitive-information disclosure** — system-prompt leak, secrets/PII surfaced in output.
   - **Data exfiltration** — model coaxed into sending data to an attacker-controlled sink (a tool, a URL, an image fetch).
   - **Tool / function abuse & excessive agency** — over-broad tool scopes, missing human-in-the-loop on destructive/irreversible actions, confused-deputy.
   - **Jailbreak / guardrail bypass** — paraphrase/obfuscation/role-play that defeats the safety layer.
   - **Insecure output handling** — model output trusted into HTML/SQL/shell/eval downstream (XSS/SSRF/RCE).
   - **Supply chain** — untrusted model/weights, third-party prompts/templates, plugins/MCP servers.
   - **Denial-of-wallet / DoS** — unbounded token spend, recursive tool loops, no rate/spend cap.
4. **Rate** each: likelihood (low/med/high) × impact (low/med/high), with one line of reasoning grounded in the design.
5. **Mitigate** each with a CONCRETE control tied to the component (e.g. "fence retrieved content as data not instructions in `agent/prompt.py:N`"; "scope tool X read-only + require confirm on the delete path"; "spend cap per session"). No generic "validate input".
6. **Write** the findings to `docs/threat-models/<system-slug>.md` (create the dir if absent). Frame the taxonomy as the OWASP LLM Top-10 WITHOUT inventing rule IDs or specifics you can't ground.

## Output
- `docs/threat-models/<system-slug>.md`: the surface map + a threat table — `threat | class | component (file:line) | likelihood×impact | mitigation` — and a top-N "fix first" list ordered by risk.
- A one-line carve reminder: this is the design-time map; the runtime `security-guardrail` agent is what judges live prompts.

## Refuses when
- `llm_provider` is `none` / unset — there is no LLM surface to model; say so and stop.
- Asked to JUDGE or BLOCK a live prompt (that is the runtime `security-guardrail` agent), or to run SAST/SBOM on a diff (`security-review`) — this produces a document, it does not gate.
- Asked to threat-model a system without reading the repo — it grounds threats in real components, it does not narrate a generic checklist.
