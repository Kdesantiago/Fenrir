#!/usr/bin/env bash
# fenrir Monitor — streams AKS rollout status + error-log lines to Claude.
# Each stdout line is delivered to Claude as a notification, so it reacts to rollout
# failures / error spikes without being asked to start watching.
#
# Config via env (set in your shell or .claude/settings.json env):
#   DS_K8S_DEPLOYMENT  (e.g. deploy/service-a)  — required for rollout watch
#   DS_K8S_NAMESPACE   (default: default)
#   DS_ERROR_LOG       (path to tail, optional)
#   DS_KUBECTL         (wrapper, may include args, e.g. "mycorp-kubectl --ctx prod"; default: kubectl)
# If stack-interface.yaml declares a kubectl wrapper, set DS_KUBECTL to it.
set -uo pipefail

read -ra KUBECTL <<< "${DS_KUBECTL:-kubectl}"   # supports a wrapper with args
NS="${DS_K8S_NAMESPACE:-default}"
DEPLOY="${DS_K8S_DEPLOYMENT:-}"
LOG="${DS_ERROR_LOG:-}"

TAIL_PID=""
cleanup() { [ -n "$TAIL_PID" ] && kill "$TAIL_PID" 2>/dev/null; }
trap cleanup EXIT INT TERM

# Tail an error log in the background if configured (line-buffered so lines arrive live).
if [ -n "$LOG" ] && [ -f "$LOG" ]; then
  ( tail -n0 -F "$LOG" 2>/dev/null | stdbuf -oL sed 's/^/[error-log] /' ) &
  TAIL_PID=$!
fi

# Poll rollout status every 5s; emit on change. Exits when rollout completes/fails.
if [ -n "$DEPLOY" ] && command -v "${KUBECTL[0]}" >/dev/null 2>&1; then
  last=""
  for _ in $(seq 1 133); do   # ~20 min cap (≈9s/iter: 4s timeout + 5s sleep)
    cur="$("${KUBECTL[@]}" -n "$NS" rollout status "$DEPLOY" --timeout=4s 2>&1)"
    if [ "$cur" != "$last" ]; then
      echo "[rollout] $cur"
      last="$cur"
    fi
    case "$cur" in
      *successfully\ rolled\ out*) echo "[rollout] DONE"; break ;;
    esac
    sleep 5
  done
else
  echo "[aks-deploy-watch] set DS_K8S_DEPLOYMENT (and DS_KUBECTL if you use a wrapper) to watch a rollout."
fi
# No trailing `wait` — the rollout loop is the lifecycle; the trap kills the tail on exit.
