"""
tests/test_participation_mirror.py
----------------------------------
`web/src/lib/participation.ts:participationRedemption` is a hand-written mirror of
`core/note.py:_participation_redemption`. The TS one draws the payoff-profile
diagram; the Python one prices the note. CLAUDE.md says "keep the two in sync"
and nothing enforced it — the repo has no JS test runner, so a drift between the
picture a client is shown and the payoff they are sold was caught by reading.

This runs BOTH implementations over the same grid and compares. No new toolchain:
the TS file's only import is a TYPE, which erases, so `tsc` (already in the web
devDependencies) transpiles it standalone and Node runs it.

Skips when Node or the web toolchain is absent, which is the light CI job; the
`web` job has both, and this is cheap enough to run everywhere else.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile

import numpy as np
import pytest

from core.note import NoteTerms, _participation_redemption

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_TS = _ROOT / "web/src/lib/participation.ts"
_TSC = _ROOT / "web/node_modules/.bin/tsc"

pytestmark = pytest.mark.skipif(
    not (shutil.which("node") and _TSC.exists() and _TS.exists()),
    reason="node / web toolchain absent — the web CI job covers this")


# Every downside x upside combination, plus the parameters that select between
# their branches. Deliberately includes a strike ABOVE par (the case where the
# `full` floor used to pay uncapped upside) and a knock-out rebate BELOW par.
_CASES: list[dict] = [
    {"participation_downside": d, "participation_upside": u,
     "participation_strike": s, "participation_rate": r,
     "protection_level": p, "upside_cap": c,
     "knockout_level": ko, "knockout_payout": kp, "digital_payout": dp}
    for d in ("full", "buffer", "airbag", "bear")
    for u in ("linear", "shark_fin", "digital")
    for s in (1.0, 1.10, 0.95)
    for r, c in ((1.0, 0.30), (2.0, None), (0.5, 0.15))
    for p in (0.90, 1.0, 0.60)
    for ko, kp in ((1.40, 0.95), (1.25, 1.05))
    for dp in (0.10,)
]
_LEVELS = [0.0, 0.25, 0.5, 0.75, 0.9, 0.999, 1.0, 1.05, 1.1, 1.2, 1.3, 1.5, 2.0, 3.0]


def _terms(over: dict) -> NoteTerms:
    d = {"name": "M", "note_type": "participation", "maturity": 1.0,
         "payment_freq": "annual", "coupon_pa": 0.0, "coupon_barrier": 0.0,
         "autocall_barrier": 2.0, "autocall_start_period": 99,
         "knock_in_barrier": 0.0, "tickers": {"A": "A"}}
    d.update({k: v for k, v in over.items() if v is not None})
    return NoteTerms.from_dict(d)


def _run_ts(payload: list[dict]) -> list[float]:
    """Transpile the mirror and evaluate it in Node."""
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        (t / "p.ts").write_text(_TS.read_text())
        # Type resolution fails (the NoteTerms import points outside the temp
        # dir) but emit still happens and `import type` erases — so the JS is
        # complete. Errors are ignored deliberately; a REAL syntax problem shows
        # up as a missing p.js and fails loudly below.
        subprocess.run([str(_TSC), "p.ts", "--target", "es2020", "--module",
                        "es2020", "--skipLibCheck"], cwd=t, capture_output=True)
        js = t / "p.js"
        assert js.exists(), "tsc emitted nothing — the mirror does not compile"
        # Payload goes through a FILE, not argv — the grid below is ~9 000 points
        # and argv blew the OS limit.
        (t / "cases.json").write_text(json.dumps(payload))
        (t / "run.mjs").write_text(
            "import { participationRedemption } from './p.js'\n"
            "import { readFileSync } from 'node:fs'\n"
            "const cs = JSON.parse(readFileSync('cases.json', 'utf8'))\n"
            "console.log(JSON.stringify(cs.map(c => participationRedemption(c.B, c.t))))\n")
        out = subprocess.run(["node", "run.mjs"], cwd=t, capture_output=True, text=True)
        assert out.returncode == 0, f"node failed: {out.stderr[-800:]}"
        return json.loads(out.stdout)


def test_the_typescript_mirror_matches_the_priced_payoff():
    """Same inputs, same redemption — across every style combination.

    Mutation-verified: changing either side's `full` branch (the one edited most
    recently, to cap the floor at par for a strike above par) makes this fail
    with the exact basket level that diverges.
    """
    payload, expected, labels = [], [], []
    for over in _CASES:
        t = _terms(over)
        py = _participation_redemption(np.asarray(_LEVELS, dtype=float), t)
        # The TS side reads the raw config fields, so hand it the same values the
        # Python object resolved — anything absent is `null`, which its `??`
        # defaults handle exactly as the Python `getattr` defaults do.
        ts_terms = {k: getattr(t, k, None) for k in (
            "participation_strike", "participation_rate", "protection_level",
            "upside_cap", "participation_upside", "participation_downside",
            "knockout_level", "knockout_payout", "digital_payout")}
        for B, want in zip(_LEVELS, py):
            payload.append({"B": B, "t": ts_terms})
            expected.append(float(want))
            labels.append(f"{over['participation_downside']}/"
                          f"{over['participation_upside']} strike="
                          f"{over['participation_strike']} rate={over['participation_rate']} "
                          f"cap={over['upside_cap']} prot={over['protection_level']} B={B}")

    got = _run_ts(payload)
    assert len(got) == len(expected)
    bad = [(lbl, g, w) for lbl, g, w in zip(labels, got, expected)
           if abs(g - w) > 1e-9]
    assert not bad, (
        f"{len(bad)} of {len(expected)} points diverge between the TS diagram and "
        f"the priced payoff. First 5:\n" +
        "\n".join(f"  {lbl}: TS {g:.6f} vs Python {w:.6f}" for lbl, g, w in bad[:5]))
