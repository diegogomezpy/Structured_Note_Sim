#!/usr/bin/env bash
# The gate every extraction slice must pass, with exit codes that actually gate.
#
# Written because a hand-rolled `pytest … | grep … && git commit` chain gates on
# GREP's exit status, not pytest's — so a red suite committed anyway. Each check
# here is run bare and its status captured.
#
#   1. full test suite
#   2. tests/golden/hashes.json unchanged in git  (a re-baseline is not a pass)
#   3. all 16 documents byte-identical to the captured baseline
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

fail=0

echo "── 1/3  test suite ─────────────────────────────────────────"
python3 -m pytest tests/ -q 2>&1 | tail -3
if [ "${PIPESTATUS[0]}" -ne 0 ]; then echo "   FAIL: tests"; fail=1; fi

echo "── 2/3  golden hashes untouched ────────────────────────────"
if git diff --quiet -- tests/golden/hashes.json && \
   git diff --cached --quiet -- tests/golden/hashes.json; then
  echo "   ok: hashes.json unmodified"
else
  echo "   FAIL: hashes.json changed — a pure code move must not need a re-baseline"
  fail=1
fi

echo "── 3/3  document fingerprints ──────────────────────────────"
python3 scripts/pdf_baseline.py check 2>&1 | grep -vE "^\[PDF (logo|font)" | tail -3
if [ "${PIPESTATUS[0]}" -ne 0 ]; then echo "   FAIL: rendered output moved"; fail=1; fi

if [ "$fail" -eq 0 ]; then
  echo "── GATE PASSED ─────────────────────────────────────────────"
else
  echo "── GATE FAILED — do not commit ─────────────────────────────"
fi
exit "$fail"
