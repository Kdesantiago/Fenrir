# Security Policy

Fenrir ships security-enforcement machinery — in-session guard hooks
(`delivery-guard`, `prompt-guard`, `content-scanner`), secret-scan wiring, SAST/SBOM
templates, and branch-protection-as-code. A flaw here can weaken the gate on every repo
that installed the plugin, so disclosure matters.

## Reporting a vulnerability

**Do not open a public issue for a security problem.** Report privately:

- Preferred: GitHub **Security Advisories** → *Report a vulnerability* on this repo
  (Security tab), which opens a private channel.
- Or email **kylliann.desantiago@gmail.com** with `[FENRIR SECURITY]` in the subject.

Please include: affected component (hook / template / skill / agent), version or commit,
a reproduction, and the impact (what protection is bypassed or weakened).

You'll get an acknowledgement within a few days. Please allow a reasonable window for a
fix before any public disclosure.

## What's in scope

- A guard hook that fails **open** when it should fail closed (e.g. `delivery-guard`
  allowing a mutating tool call on malformed input, a `--no-verify` / secret-exfil /
  force-push bypass slipping through).
- `prompt-guard` / `content-scanner` missing a class of injection it claims to catch.
- A template that emits an insecure default (secret literal, over-broad permission,
  unsigned image where signing is declared).
- Secret material committed to the repo.

## Not in scope

- The documented best-effort limits of regex command-scanning (the hooks state plainly
  they are not a sandbox; the OS/CI controls are authoritative).
- Findings that require already having write access to a victim's `.claude/` settings.

## Supported versions

Only the latest released `MAJOR.MINOR` receives security fixes. Consumers should pin a
released plugin version and track updates via Renovate.
