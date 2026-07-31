"""
core/compare.py
----------------
A/B comparison statistics — pure numpy over price_note payoff dicts.

Lives in core/ (no web, plotly or file-I/O imports) because it IS quant, not
API plumbing: it reads the same per-path arrays price_note returns and gives
back numbers. api/engine.py builds the figures and serialises; this module
decides what the comparison actually says.

The central idea is PAIRING. When two notes are priced on one shared
simulation, index i is the same simulated world for both, so the per-path
difference is a real quantity rather than a difference of two independent
averages — and its standard error is far tighter, because the market risk
cancels and only the term effect is left.
"""
from __future__ import annotations

import numpy as np

from core.note import NoteTerms


def _finite(x) -> float | None:
    """float(x) when it is a real number, else None (mirrors the API helper).""" 
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None

def share_blockers(terms_a: NoteTerms, terms_b: NoteTerms) -> list[str]:
    """Why an A/B compare can NOT price both notes on ONE set of simulated paths.

    They must live on the same trading-day grid AND the same performance scale.
    Being HELD changes both — the grid runs to the ORIGINAL maturity and performance
    is measured against the ORIGINAL fixings — so a held B can only ride A's paths
    when it is held off the very same issue date.

    Empty list = shareable. Otherwise the reasons, so the UI can say what to change
    rather than just reporting that the comparison is noisier."""
    out = []
    # Compare the SYMBOLS as a set — not the whole {ticker: display-name} mapping.
    # A basket is a set (worst-of / best-of / average all reduce across assets, so
    # order cannot matter), and the display name is pure presentation: comparing
    # dicts meant renaming "Apple" to "Apple Inc." in one config silently dropped
    # the pairing and turned a tight paired comparison into two independent ones,
    # with no term of the note actually changed.
    if set(terms_a.tickers) != set(terms_b.tickers):
        out.append("underlyings")
    if abs(float(terms_a.maturity) - float(terms_b.maturity)) >= 1e-9:
        out.append("maturity")
    if bool(terms_a.is_held) != bool(terms_b.is_held):
        out.append("held")
    elif terms_a.is_held and terms_a.issue_date != terms_b.issue_date:
        out.append("issue_date")
    return out


def can_share_paths(terms_a: NoteTerms, terms_b: NoteTerms) -> bool:
    """Whether an A/B compare can share one simulation — see share_blockers."""
    return not share_blockers(terms_a, terms_b)


# ── paired analytics ──────────────────────────────────────────────────────────
# Only meaningful on shared paths: index i is the SAME simulated world for both
# notes, so the per-path difference is a real quantity rather than a difference
# of two independent averages — and its standard error is far tighter, because
# the market risk cancels and only the term effect remains.

def outcome_buckets(note: dict, terms: NoteTerms) -> tuple[np.ndarray, list[str]]:
    """Per-path resolution as a small categorical, plus its labels. Autocall
    resolves as called-early / redeemed-at-par / knocked-in; a participation note
    has no autocall, so it resolves by where the redemption landed."""
    if getattr(terms, "note_type", "autocall") == "participation":
        R = np.asarray(note["nominal_payoffs"], dtype=float)
        code = np.where(R < 1.0 - 1e-9, 0, np.where(R > 1.0 + 1e-9, 2, 1))
        return code, ["part_loss", "part_par", "part_gain"]
    called = np.asarray(note["autocall_period"], dtype=int) > 0
    ki = np.asarray(note["knock_in_triggered"], dtype=bool)
    code = np.where(called, 0, np.where(ki, 2, 1))
    return code, ["out_called", "out_par", "out_ki"]


def paired_stats(note_a: dict, note_b: dict, terms_a: NoteTerms, terms_b: NoteTerms) -> dict:
    """Head-to-head statistics over the paired per-path outcomes.

    `win_rate` is the headline the summary means can't give you: a +0.8% mean edge
    that wins on 51% of paths is a different product from one that wins on 88%.
    `se_edge` is the standard error OF THE PAIRED DIFFERENCE — compare it to the
    edge itself to see whether the difference is signal or Monte-Carlo noise."""
    ta = np.asarray(note_a["total_returns"], dtype=float)
    tb = np.asarray(note_b["total_returns"], dtype=float)
    ia = np.asarray(note_a["annualized_returns"], dtype=float)
    ib = np.asarray(note_b["annualized_returns"], dtype=float)
    n = int(min(ta.size, tb.size))
    ta, tb, ia, ib = ta[:n], tb[:n], ia[:n], ib[:n]
    d_tot, d_irr = tb - ta, ib - ia
    tol = 1e-12

    code_a, labels_a = outcome_buckets(note_a, terms_a)
    code_b, labels_b = outcome_buckets(note_b, terms_b)
    k = len(labels_a)
    # matrix[i][j] = fraction of paths resolving as A-bucket i and B-bucket j.
    matrix = np.zeros((k, k), dtype=float)
    for i in range(k):
        sel = code_a[:n] == i
        if not sel.any():
            continue
        for j in range(k):
            matrix[i, j] = float((code_b[:n][sel] == j).sum()) / n

    # Conditional tails — the question a client actually asks: when the note I
    # hold goes wrong, does the alternative go wrong too?
    a_bad, b_bad = ta < 0, tb < 0
    cond = {
        "a_loss_rate":        float(a_bad.mean()),
        "b_loss_rate":        float(b_bad.mean()),
        # of the paths where A loses money, how often does B also lose?
        "b_loses_given_a":    float(b_bad[a_bad].mean()) if a_bad.any() else None,
        "a_loses_given_b":    float(a_bad[b_bad].mean()) if b_bad.any() else None,
        # and how much better/worse is B on exactly A's bad paths?
        "edge_on_a_losses":   float(d_tot[a_bad].mean()) if a_bad.any() else None,
    }
    return {
        "n_paths":      n,
        "win_rate":     float((d_tot > tol).mean()),
        "tie_rate":     float((np.abs(d_tot) <= tol).mean()),
        "loss_rate":    float((d_tot < -tol).mean()),
        "mean_edge":    float(d_tot.mean()),
        "median_edge":  float(np.median(d_tot)),
        "mean_edge_irr":   float(d_irr.mean()),
        "median_edge_irr": float(np.median(d_irr)),
        "edge_p5":      float(np.percentile(d_tot, 5)),
        "edge_p95":     float(np.percentile(d_tot, 95)),
        "se_edge":      float(d_tot.std(ddof=1) / np.sqrt(n)) if n > 1 else None,
        "se_edge_irr":  float(d_irr.std(ddof=1) / np.sqrt(n)) if n > 1 else None,
        "transition":   [[float(v) for v in row] for row in matrix],
        "labels":       labels_a if labels_a == labels_b else labels_a,
        "mixed_types":  labels_a != labels_b,
        "conditional":  cond,
    }



def metric_samples(note: dict, key: str, terms: NoteTerms | None = None) -> np.ndarray | None:
    """The per-path sample behind a summary metric, where one exists — so the
    table can report how precise each figure actually is. Quantiles and
    conditional means (p5_redemption, avg_time_to_autocall) have no clean
    closed-form standard error, so they return None and the row shows no ±.

    `terms` is needed only by the two participation probabilities whose threshold
    lives on the term sheet rather than in the payoff dict (the redemption cap and
    the knock-out level). Without it they fall through to None, which is what a
    caller that has no terms should get — not a missing row."""
    if key == "expected_irr":
        return np.asarray(note["annualized_returns"], dtype=float)
    if key == "expected_total_return":
        return np.asarray(note["total_returns"], dtype=float)
    if key == "expected_coupon":
        return np.asarray(note["coupon_payoffs"], dtype=float)
    if key in ("expected_nominal_payout", "expected_redemption"):
        return np.asarray(note["nominal_payoffs"], dtype=float)
    if key == "expected_gain":
        return np.maximum(np.asarray(note["nominal_payoffs"], dtype=float) - 1.0, 0.0)
    if key == "prob_autocall":
        return (np.asarray(note["autocall_period"], dtype=int) > 0).astype(float)
    if key == "prob_knock_in_total":
        return np.asarray(note["knock_in_triggered"], dtype=bool).astype(float)
    if key == "prob_loss":
        return (np.asarray(note["total_returns"], dtype=float) < 0).astype(float)
    if key == "prob_above_par":
        return (np.asarray(note["nominal_payoffs"], dtype=float) > 1.0 + 1e-9).astype(float)
    # Both of these are plain binomials over the same paths as every other row, so
    # there is no reason for them to be the only two participation metrics printed
    # without a ± — they were simply never given a case here. Thresholds must match
    # core/note.py:_participation_stats exactly, or the error bar would describe a
    # different event from the estimate it hangs off.
    if key == "prob_at_cap" and terms is not None:
        if (terms.upside_cap is None
                or getattr(terms, "participation_periodic", False)):
            return None                       # no redemption ceiling — see _participation_stats
        cap_lv = 1.0 + float(terms.participation_rate) * float(terms.upside_cap)
        R = np.asarray(note["nominal_payoffs"], dtype=float)
        return (R >= cap_lv - 1e-6).astype(float)
    if key == "prob_knocked_out" and terms is not None:
        B = note.get("final_basket")
        if (B is None or terms.knockout_level is None
                or terms.participation_upside != "shark_fin"):
            return None
        return (np.asarray(B, dtype=float) >= float(terms.knockout_level)).astype(float)
    return None


def compare_diff(sum_a: dict, sum_b: dict, terms_a: NoteTerms, terms_b: NoteTerms,
                  note_a: dict | None = None, note_b: dict | None = None,
                  shared: bool = False) -> dict:
    """Metric-by-metric A · B · Δ table data. Only metrics meaningful for BOTH
    note types are surfaced; the client renders/formats per metric.

    Each row also carries `se` — the standard error of the DELTA. On shared paths
    that is the SE of the paired difference (market risk cancels, so it is far
    tighter than either side's own error); otherwise the two independent errors
    are combined in quadrature. A delta smaller than ~2×se is Monte-Carlo noise,
    and the client marks it as such instead of letting the reader over-read it."""
    both_part = sum_a.get("note_type") == "participation" and sum_b.get("note_type") == "participation"
    # NB: for a Autocall note `expected_nominal_payout` is just `expected_total_return
    # + 100%` (it folds coupons into "redemption"), so it's deliberately omitted here
    # — it's redundant with total return and its "redemption" label misleads. It's
    # kept for Participation, where there are no coupons and it IS the redemption.
    keys = (["expected_irr", "expected_total_return", "expected_gain", "prob_above_par",
             "prob_at_cap", "prob_knocked_out", "p5_redemption"] if both_part else
            ["expected_irr", "expected_total_return", "expected_coupon", "prob_autocall",
             "prob_knock_in_total", "avg_time_to_autocall"])
    # P(loss) belongs on every comparison — it is the metric a purchase price
    # moves, and it is not the knock-in rate.
    keys.append("prob_loss")

    def _se(key: str) -> float | None:
        if note_a is None or note_b is None:
            return None
        xa = metric_samples(note_a, key, terms_a)
        xb = metric_samples(note_b, key, terms_b)
        if xa is None or xb is None or xa.size < 2 or xb.size < 2:
            return None
        if shared and xa.size == xb.size:
            d = xb - xa
            return float(d.std(ddof=1) / np.sqrt(d.size))
        va = xa.var(ddof=1) / xa.size
        vb = xb.var(ddof=1) / xb.size
        return float(np.sqrt(va + vb))

    rows = []
    for k in keys:
        a, b = sum_a.get(k), sum_b.get(k)
        if a is None and b is None:
            continue
        d = (b - a) if (isinstance(a, (int, float)) and isinstance(b, (int, float))) else None
        rows.append({"key": k, "a": a, "b": b, "delta": d, "se": _finite(_se(k))})
    # Cost basis is a term of the POSITION, not an estimate — no error bar, and
    # only worth a row when the two sides actually differ.
    ca, cb = float(terms_a.cost_basis), float(terms_b.cost_basis)
    if abs(ca - 1.0) > 1e-9 or abs(cb - 1.0) > 1e-9:
        rows.append({"key": "cost_basis", "a": ca, "b": cb, "delta": cb - ca, "se": None})
    return {"rows": rows, "both_participation": both_part}
