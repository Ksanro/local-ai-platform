#!/bin/sh
# Pre-commit test gate for the live gateway path (tracked; the local
# .git/hooks/pre-commit wrapper delegates here).
#
# Default mode: run the live-path test set and block the commit on pytest's
# exit code. No failure-count parsing.
#
# --full mode: run the full suite and allow the known dormant-package
# failure baseline (43 failures on Python 3.13). Exit 1 if the count
# exceeds the baseline or if the run cannot be interpreted safely.
#
# See TESTING.md "Pre-commit hook" and CLAUDE.md "Test baseline".

set -u

root=$(git rev-parse --show-toplevel) || exit 1
cd "$root" || exit 1

baseline=43

if [ -n "${1:-}" ]; then
  if [ "$1" != "--full" ]; then
    echo "pre-commit: ERROR: unknown argument: $1"
    echo "usage: precommit_test_gate.sh [--full]"
    exit 1
  fi
  run_full=1
else
  run_full=0
fi

if command -v uv >/dev/null 2>&1; then
  uv_cmd=uv
elif [ -x "./uv" ]; then
  uv_cmd=./uv
elif [ -x "./uv.exe" ]; then
  uv_cmd=./uv.exe
else
  echo "pre-commit: ERROR: uv not found on PATH or in the repo root."
  exit 1
fi

if [ "$run_full" -eq 0 ]; then
  echo "pre-commit: live gate (pytest, live-path tests only)..."
  "$uv_cmd" run python -m pytest -q \
    tests/pipeline \
    tests/gateway \
    tests/providers \
    tests/planning \
    tests/context \
    tests/repository \
    tests/evaluation \
    tests/scripts \
    tests/engineering_memory \
    tests/test_protocol_invariant.py \
    tests/observability/test_quality_harness.py \
    tests/observability/test_quality_history.py \
    tests/observability/test_session_log_history.py
  code=$?
  if [ "$code" -eq 0 ]; then
    echo "pre-commit: live gate OK"
  else
    echo "pre-commit: live gate FAILED (pytest exit $code)"
  fi
  exit "$code"
fi

echo "pre-commit: full suite (baseline $baseline failures on Python 3.13)..."
output=$("$uv_cmd" run python -m pytest -q 2>&1)
code=$?
printf '%s\n' "$output"

if [ "$code" -eq 0 ]; then
  echo "pre-commit: full suite OK (0 failures, baseline $baseline)"
  exit 0
fi

if [ "$code" -ne 1 ]; then
  echo "pre-commit: full suite FAILED (pytest exit $code; collection or internal error, not interpretable as a failure count)."
  exit 1
fi

# Exit 1 means test failures: parse only the final pytest summary line, e.g.
# "43 failed, 2275 passed in 45.12s".
summary=$(printf '%s\n' "$output" | grep -E '^[0-9]+ (failed|passed).* in [0-9.]+s' | tail -n 1)
if [ -z "$summary" ]; then
  echo "pre-commit: full suite FAILED (pytest exit 1 but no parseable summary line; not safe to interpret)."
  exit 1
fi

case "$summary" in
  *" failed"*) ;;
  *)
    echo "pre-commit: full suite FAILED (pytest exit 1 but no 'N failed' in summary: $summary)."
    exit 1
    ;;
esac

fails=$(printf '%s\n' "$summary" | sed -E 's/^([0-9]+) failed.*/\1/')
if [ -z "$fails" ]; then
  echo "pre-commit: full suite FAILED (could not extract failure count from: $summary)."
  exit 1
fi

if [ "$fails" -gt "$baseline" ]; then
  echo "pre-commit: full suite FAILED ($fails failures exceed baseline $baseline)."
  exit 1
fi

echo "pre-commit: full suite OK ($fails failures, baseline $baseline)"
exit 0
