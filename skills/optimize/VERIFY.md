# VERIFY — optimize

Run after `optimize` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] exactly ONE constraint was stated and is the metric reported: the report names a single `latency | throughput | memory | cost | bundle-size | cold-start` target — `grep -aiE 'constraint|metric' <report> | grep -qiE 'latency|throughput|memory|cost|bundle|cold-start' && echo OK || echo MISSING`
- [ ] a BEFORE baseline is recorded with the exact reproducible command and variance (median over N≥5 runs, not a single sample): `grep -aiE 'before|baseline' <report> && echo OK || echo MISSING`
- [ ] the AFTER measurement uses the SAME harness/command as BEFORE and the report states the measured `%delta`: `grep -aiE 'after|%?delta' <report> && echo OK || echo MISSING`
- [ ] behavior-unchanged: the test suite passes identically before and after — the report carries the attestation and the runner is green: `pytest -q >/dev/null 2>&1 && echo OK || echo "RUN TEST SUITE"`
- [ ] no optimization is claimed without a measured improvement beyond noise/variance — the report carries a numeric delta AND a numeric stddev, and `|delta| > stddev`: `D=$(grep -aioE 'delta[^0-9.-]*-?[0-9.]+' <report> | grep -oE '\-?[0-9.]+' | tail -1); S=$(grep -aioE '(stddev|std|variance)[^0-9.-]*[0-9.]+' <report> | grep -oE '[0-9.]+' | tail -1); if [ -n "$D" ] && [ -n "$S" ]; then awk -v d="$D" -v s="$S" 'BEGIN{d=(d<0?-d:d); print (d>s)?"OK delta>stddev":"FAIL within variance — revert"}'; else echo "MISSING numeric delta/stddev"; fi
- [ ] the change is minimal and attributable: the report cites a `file:line` bottleneck and the diff touches ≤ 3 files (one hypothesis, not a blanket rewrite): `grep -aqE '[A-Za-z0-9_./-]+:[0-9]+' <report> && N=$(git diff --name-only HEAD | grep -cvE '\.md$') && [ "$N" -le 3 ] && echo "OK ($N files)" || echo "FAIL — no file:line citation or >3 files changed"`
- [ ] matches `org-profile.yaml`: the harness chosen fits the declared `framework`/`platform` for the stated metric

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v pytest` · `command -v py-spy` · `python -c 'import pytest_benchmark' 2>/dev/null` (latency) · `python -c 'import memory_profiler' 2>/dev/null` (memory) · `command -v node` / a bundler stats tool (front bundle-size) — note absent, don't fail

## Functional
- Re-run the exact command recorded in the BEFORE/AFTER report against the same representative workload: the after-number reproduces within the reported variance and beats the before-number by the claimed `%delta`. Confirm the test suite is identical (same pass set) before and after, proving the win preserved behavior — a perf gain that changes outputs or sits within noise is not a valid result.
