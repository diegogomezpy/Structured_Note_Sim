#!/usr/bin/env bash
# The gate every extraction slice must pass, with exit codes that actually gate.
#
# Written because a hand-rolled `pytest … | grep … && git commit` chain gates on
# GREP's exit status, not pytest's — so a red suite committed anyway. Each check
# here is run bare and its status captured.
#
#   1. full test suite
#   2. tests/golden/hashes.json unchanged in git  (a re-baseline is not a pass)
#   3. every document byte-identical to the captured baseline
#      (the matrix is THEMES x KINDS x LANGS in scripts/pdf_baseline.py)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

fail=0

echo "── 1/3  test suite ─────────────────────────────────────────"
python3 -m pytest tests/ -q 2>&1 | tail -3
if [ "${PIPESTATUS[0]}" -ne 0 ]; then echo "   FAIL: tests"; fail=1; fi

echo "── 2/3  golden baselines not re-based ──────────────────────"
# The invariant is not "the file is untouched" — ADDING a fixture is legitimate
# and desirable. It is "no EXISTING baseline moved": a pure code move must never
# change a page that was already pinned. Distinguishing the two is the whole
# point, because "I added a fixture" and "I quietly re-baselined" look identical
# to `git diff --quiet`.
python3 - <<'PYGATE'
import json, subprocess, sys
try:
    old = json.loads(subprocess.run(
        ["git", "show", "HEAD:tests/golden/hashes.json"],
        capture_output=True, text=True, check=True).stdout)
except Exception:
    print("   skip: no committed baseline to compare against"); sys.exit(0)
new = json.loads(open("tests/golden/hashes.json").read())
moved = sorted(k for k in old if old[k] != new.get(k))
added = sorted(set(new) - set(old))
if moved:
    print(f"   FAIL: {len(moved)} existing baseline(s) RE-BASED: {moved}")
    sys.exit(1)
print(f"   ok: {len(old)} existing baselines unchanged"
      + (f", {len(added)} added ({', '.join(added)})" if added else ""))
PYGATE
if [ "$?" -ne 0 ]; then fail=1; fi

echo "── 3/3  document fingerprints ──────────────────────────────"
python3 scripts/pdf_baseline.py check 2>&1 | grep -vE "^\[PDF (logo|font)" | tail -3
if [ "${PIPESTATUS[0]}" -ne 0 ]; then echo "   FAIL: rendered output moved"; fail=1; fi

if [ "$fail" -eq 0 ]; then
  echo "── GATE PASSED ─────────────────────────────────────────────"
else
  echo "── GATE FAILED — do not commit ─────────────────────────────"
fi
exit "$fail"
