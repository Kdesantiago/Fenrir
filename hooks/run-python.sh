#!/usr/bin/env bash
# Cross-OS Python launcher for plugin-level (static) hooks. Invoked in SHELL form from
# hooks.json so it runs under sh -c (macOS/Linux) or Git Bash (Windows). Probes a real
# interpreter and exec's it. Fail-open: if none found, exit 0 (tracking is best-effort).
# Requires Python >=3.9 (the hooks use from __future__ import annotations + timezone.utc).
set -u
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then exec "$cand" "$@"; fi
done
if command -v py >/dev/null 2>&1; then exec py -3 "$@"; fi   # Windows python.org launcher
exit 0
