# VERIFY — optimize

Run after `optimize` has been applied to a repo. All BLOCKING checks must pass.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] exactly ONE constraint was stated and is the metric reported: the report names a single `latency | throughput | memory | cost | bundle-size | cold-start` target — `grep -aiE 'constraint|metric' <report> | grep -qiE 'latency|throughput|memory|cost|bundle|cold-start' && echo OK || echo MISSING`
- [ ] a BEFORE baseline is recorded with the exact reproducible command and variance (median over N≥5 runs, not a single sample): `grep -aiE 'before|baseline' <report> && echo OK || echo MISSING`
- [ ] the AFTER measurement uses the SAME harness/command as BEFORE and the report states the measured `%delta`: `grep -aiE 'after|%?delta' <report> && echo OK || echo MISSING`
- [ ] behavior-unchanged: the test suite passes identically before and after — the report carries the attestation and the runner is green: `pytest -q >/dev/null 2>&1 && echo OK || echo "RUN TEST SUITE"`
- [ ] no optimization is claimed without a measured improvement beyond noise/variance (a within-variance result was reverted, not shipped) — the delta exceeds the reported stddev
- [ ] the change is minimal and attributable: one hypothesis, citing the `file:line` / profiler output for the bottleneck, not a blanket rewrite
- [ ] matches `org-profile.yaml`: the harness chosen fits the declared `framework`/`platform` for the stated metric

## Informational (tooling presence — does NOT block; note if absent)
- [ ] `command -v pytest` · `command -v py-spy` · `python -c 'import pytest_benchmark' 2>/dev/null` (latency) · `python -c 'import memory_profiler' 2>/dev/null` (memory) · `command -v node` / a bundler stats tool (front bundle-size) — note absent, don't fail

## Functional
- Re-run the exact command recorded in the BEFORE/AFTER report against the same representative workload: the after-number reproduces within the reported variance and beats the before-number by the claimed `%delta`. Confirm the test suite is identical (same pass set) before and after, proving the win preserved behavior — a perf gain that changes outputs or sits within noise is not a valid result.
