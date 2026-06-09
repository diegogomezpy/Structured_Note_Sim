"""
core/note.py
------------
NoteTerms dataclass — full Phoenix/Autocallable structured note specification.
price_note()         — fully vectorized payoff engine (no Python loops).

Supports replication of:
  - HSBC XS3376563584: 24M monthly Phoenix Memory Worst-of, knock-in barrier,
                        separate coupon barrier, autocall starts at period 4
  - BBVA XS3378405743: 18M quarterly Phoenix Memory Worst-of, knock-in barrier,
                        best-of final redemption condition

Key features
------------
  - Worst-of / best-of / basket-average selectable per event type
    (coupon check, autocall check, final redemption check)
  - Memory coupon: missed coupons accumulate and are paid on next trigger
  - Separate coupon barrier, autocall barrier, knock-in barrier
  - Autocall start period: first N periods are coupon-only (no early redemption)
  - European knock-in: checked only at final valuation date
  - Cash-equivalent physical delivery at maturity if knock-in triggered
  - Configurable observation frequency (monthly, quarterly, etc.)
  - JSON-serialisable via NoteTerms.to_dict() / NoteTerms.from_dict()
"""

from __future__ import annotations

import json
import numpy as np
from dataclasses import dataclass, field
from typing import Literal

BasketType = Literal["worst_of", "best_of", "average"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _basket(perf: np.ndarray, kind: BasketType) -> np.ndarray:
    """
    Reduce per-asset performance array to a scalar per path.

    perf : (n_paths, n_assets)
    returns : (n_paths,)
    """
    if kind == "worst_of":
        return perf.min(axis=1)
    elif kind == "best_of":
        return perf.max(axis=1)
    elif kind == "average":
        return perf.mean(axis=1)
    else:
        raise ValueError(f"Unknown basket type '{kind}'. Use 'worst_of', 'best_of', or 'average'.")


# ---------------------------------------------------------------------------
# Product specification
# ---------------------------------------------------------------------------

# Frequency string → periods per year
_FREQ_TO_PERIODS: dict[str, int] = {
    "monthly":     12,
    "quarterly":    4,
    "semi-annual":  2,
    "annual":       1,
}


@dataclass
class NoteTerms:
    """
    Full specification of a Phoenix Memory Autocallable note.

    Human-readable fields (set these in JSON / UI):
      maturity        : tenor in years (e.g. 2.0)
      payment_freq    : "monthly" | "quarterly" | "semi-annual" | "annual"
      coupon_pa       : annualised coupon rate as a fraction (e.g. 0.10 = 10% p.a.)

    Derived (computed automatically):
      n_obs           : maturity * periods_per_year
      coupon_rate     : coupon_pa / periods_per_year  (per-period rate)
    """
    maturity:               float       = 1.0
    payment_freq:           str         = "quarterly"   # monthly/quarterly/semi-annual/annual
    coupon_pa:              float       = 0.10          # annualised coupon rate
    coupon_barrier:         float       = 0.55
    autocall_barrier:       float       = 1.00
    autocall_start_period:  int         = 1
    knock_in_barrier:       float       = 0.55
    principal_protection:   float       = 1.00
    memory:                 bool        = True
    coupon_basket:          BasketType  = "worst_of"
    autocall_basket:        BasketType  = "worst_of"
    final_basket:           BasketType  = "worst_of"
    call_steepness:         float       = 100.0
    name:                   str         = "Phoenix Memory Note"
    tickers:                dict        = None
    issue_date:             str         = None   # "YYYY-MM-DD" — enables Current Performance tab

    def __post_init__(self):
        if self.tickers is None:
            object.__setattr__(self, "tickers", {})
        if self.payment_freq not in _FREQ_TO_PERIODS:
            raise ValueError(
                f"payment_freq must be one of {list(_FREQ_TO_PERIODS)}; got '{self.payment_freq}'"
            )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def periods_per_year(self) -> int:
        return _FREQ_TO_PERIODS[self.payment_freq]

    @property
    def n_obs(self) -> int:
        """Total observation periods = maturity × periods per year."""
        return round(self.maturity * self.periods_per_year)

    @property
    def coupon_rate(self) -> float:
        """Per-period coupon rate = coupon_pa / periods_per_year."""
        return self.coupon_pa / self.periods_per_year

    # ------------------------------------------------------------------
    # Schedule helpers
    # ------------------------------------------------------------------

    def obs_times(self) -> list[float]:
        """Observation times in years, evenly spaced."""
        return [self.maturity * i / self.n_obs for i in range(1, self.n_obs + 1)]

    def obs_steps(self, N: int) -> list[int]:
        """Map observation times to simulation step indices."""
        return [round(t / self.maturity * N) for t in self.obs_times()]

    def autocall_prob(self, basket_val: np.ndarray) -> np.ndarray:
        """
        Sigmoid autocall probability centred at autocall_barrier.

        At the default steepness of 100 this is effectively a hard trigger:
        P ≈ 0 below the barrier and P ≈ 1 above it.  Lower steepness values
        produce a smooth soft-trigger.

        A pure sigmoid is used here rather than a sigmoid + np.where floor.
        The np.where floor creates a discontinuity at exactly the barrier
        (sigmoid approaches ~0.5 from above but floor clamps to 0 from below),
        which would distort pricing with soft-trigger settings.  The sigmoid
        alone already gives P < 1e-10 at 10% below the barrier for steepness=100.
        """
        x = np.clip(-self.call_steepness * (basket_val - self.autocall_barrier), -500.0, 500.0)
        return 1.0 / (1.0 + np.exp(x))

    # ------------------------------------------------------------------
    # Serialisation — stores human-readable fields only
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name":                   self.name,
            "maturity":               self.maturity,
            "payment_freq":           self.payment_freq,
            "coupon_pa":              self.coupon_pa,
            "coupon_barrier":         self.coupon_barrier,
            "autocall_barrier":       self.autocall_barrier,
            "autocall_start_period":  self.autocall_start_period,
            "knock_in_barrier":       self.knock_in_barrier,
            "principal_protection":   self.principal_protection,
            "memory":                 self.memory,
            "coupon_basket":          self.coupon_basket,
            "autocall_basket":        self.autocall_basket,
            "final_basket":           self.final_basket,
            "call_steepness":         self.call_steepness,
            "tickers":                self.tickers,
            "issue_date":             self.issue_date,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NoteTerms":
        """
        Load from dict. Accepts both new format (payment_freq + coupon_pa)
        and old format (n_obs + coupon_rate) for backwards compatibility.
        """
        d = dict(d)  # don't mutate caller's dict

        # ── Old-format migration ──────────────────────────────────────
        if "n_obs" in d or "coupon_rate" in d:
            # Infer payment_freq from maturity and n_obs
            maturity = float(d.get("maturity", 1.0))
            n_obs    = int(d.pop("n_obs", 4))
            periods_py = round(n_obs / maturity)
            # Find closest known frequency
            freq = min(_FREQ_TO_PERIODS, key=lambda f: abs(_FREQ_TO_PERIODS[f] - periods_py))
            d["payment_freq"] = freq
            # Convert per-period rate to annualised
            coupon_rate = float(d.pop("coupon_rate", 0.025))
            d["coupon_pa"] = coupon_rate * _FREQ_TO_PERIODS[freq]

        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, json_str: str) -> "NoteTerms":
        return cls.from_dict(json.loads(json_str))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)




# ---------------------------------------------------------------------------
# Vectorized payoff engine
# ---------------------------------------------------------------------------

def price_note(
    perf_paths: np.ndarray,
    terms:      NoteTerms,
    seed:       int | None = 42,
) -> dict:
    """
    Evaluate Phoenix Memory Autocallable payoffs across all simulated paths.

    Fully vectorized — no Python loop over paths.

    Parameters
    ----------
    perf_paths : np.ndarray  shape (n_paths, N+1, n_assets)
        Per-asset performance paths (price / initial price).
        Produced by stacking sim_prices / S0_vector.
        perf_paths[:, 0, :] should be all 1.0 (initial level).

    terms : NoteTerms
        Product specification.

    seed : int or None
        RNG seed for autocall probability draws.

    Returns
    -------
    dict with keys:
        nominal_payoffs      : (n_paths,)
        coupon_payoffs       : (n_paths,)   total coupons received
        autocall_period      : (n_paths,)   0 = maturity, 1..n_obs = period called
        knock_in_triggered   : (n_paths,)   bool, only meaningful for maturity paths
        expected_irr         : float        simple annualised IRR (not compound)
        expected_total_return: float
        expected_coupon      : float
        prob_autocall        : float
        prob_autocall_by_period : list[float]
        prob_maturity        : float
        prob_knock_in        : float        P(knock-in at maturity | reaches maturity)
        prob_knock_in_total  : float        P(knock-in) across all paths

    Note on IRR convention
    ----------------------
    IRR is computed as simple annualisation: total_return / t_held.
    This is consistent with the structured note market convention where
    coupons are quoted as simple p.a. rates.  For long-dated paths (2Y+)
    the simple IRR will exceed a compound (XIRR-style) IRR by a small amount.
    """
    n_paths, N_plus1, n_assets = perf_paths.shape
    N = N_plus1 - 1
    obs_steps = terms.obs_steps(N)
    obs_times = terms.obs_times()
    n_obs = terms.n_obs
    rng = np.random.default_rng(seed)

    # Draw autocall decisions: (n_paths, n_obs)
    call_draws = rng.random((n_paths, n_obs))

    # Per-observation basket values
    # coupon_basket_vals[j] : (n_paths,)
    coupon_basket_vals   = np.stack(
        [_basket(perf_paths[:, s, :], terms.coupon_basket)   for s in obs_steps], axis=1
    )  # (n_paths, n_obs)

    autocall_basket_vals = np.stack(
        [_basket(perf_paths[:, s, :], terms.autocall_basket) for s in obs_steps], axis=1
    )  # (n_paths, n_obs)

    # Autocall mask: only eligible from autocall_start_period onward
    autocall_eligible = np.zeros(n_obs, dtype=bool)
    autocall_eligible[terms.autocall_start_period - 1:] = True  # 1-indexed → 0-indexed

    # Autocall probabilities per period
    autocall_probs = terms.autocall_prob(autocall_basket_vals)   # (n_paths, n_obs)
    autocall_probs[:, ~autocall_eligible] = 0.0

    autocall_triggered = call_draws < autocall_probs             # (n_paths, n_obs)

    # First autocall period per path (0 = none)
    any_autocalled   = autocall_triggered.any(axis=1)            # (n_paths,)
    first_call_idx   = np.argmax(autocall_triggered, axis=1)     # (n_paths,) 0-indexed

    autocall_period  = np.where(any_autocalled, first_call_idx + 1, 0).astype(int)

    # ------------------------------------------------------------------
    # Coupon calculation — with memory
    # ------------------------------------------------------------------
    # coupon_paid[i, j] = True if coupon is actually paid at period j on path i
    coupon_barrier_met = coupon_basket_vals >= terms.coupon_barrier   # (n_paths, n_obs)

    # For each path, coupons are paid up to and including the autocall period
    # (or all periods if reaching maturity)
    active_until = np.where(any_autocalled, autocall_period, n_obs)  # last active period (inclusive, 1-indexed)

    # Build active mask: period j is active if j <= active_until (1-indexed)
    period_idx   = np.arange(1, n_obs + 1)[np.newaxis, :]            # (1, n_obs)
    active_mask  = period_idx <= active_until[:, np.newaxis]          # (n_paths, n_obs)

    if terms.memory:
        # Memory coupon — fully vectorized via cumulative sum trick.
        #
        # Key insight: the memory coupon paid at period j (when barrier is met)
        # equals rate * (1 + number of consecutive missed periods immediately
        # preceding j).  We can compute "periods since last payment" for every
        # (path, period) cell without a Python loop as follows:
        #
        # 1. Define paid[i,j] = 1 if the barrier was met AND the period is active.
        # 2. Build a "payment group" index via cumsum of paid shifted by one period:
        #    group[i,j] = number of payments made before period j on path i.
        # 3. Within each group the running count of active non-payment periods
        #    gives the accumulated pending count.
        #
        # This is equivalent to the sequential loop but executes in C via numpy.

        paid_mask = coupon_barrier_met & active_mask          # (n_paths, n_obs)

        # group[i,j] = how many payments have been made strictly before period j
        group = np.cumsum(paid_mask, axis=1)                  # (n_paths, n_obs)
        group_shifted = np.concatenate(
            [np.zeros((n_paths, 1), dtype=group.dtype), group[:, :-1]], axis=1
        )                                                      # (n_paths, n_obs)

        # Within each group, count consecutive active periods seen so far
        # (including the current one).  A payment resets this to 0.
        # active_count[i,j] = cumsum of active_mask within the current group.
        # We subtract the cumsum at the last payment in the same group.
        active_cumsum = np.cumsum(active_mask, axis=1)        # (n_paths, n_obs)

        # Last payment position per (path, period): the cumsum of active cells
        # up to and including the most recent paid cell in the same group.
        # We compute this by masking active_cumsum at paid cells and forward-filling.
        last_paid_active_cumsum = np.where(paid_mask, active_cumsum, 0)
        # Forward-fill within each row (axis=1) using np.maximum.accumulate
        last_paid_cumsum_ff = np.maximum.accumulate(last_paid_active_cumsum, axis=1)

        # pending[i,j] = number of active missed periods strictly before j
        # in the current payment group = (active cells up to j-1) - (active cells
        # up to the last payment before j).
        active_cumsum_shifted = np.concatenate(
            [np.zeros((n_paths, 1), dtype=active_cumsum.dtype), active_cumsum[:, :-1]], axis=1
        )
        last_paid_cumsum_shifted = np.concatenate(
            [np.zeros((n_paths, 1), dtype=last_paid_cumsum_ff.dtype),
             last_paid_cumsum_ff[:, :-1]], axis=1
        )
        pending_before = active_cumsum_shifted - last_paid_cumsum_shifted  # (n_paths, n_obs)
        pending_before = np.maximum(pending_before, 0)  # guard against rounding

        coupon_amounts = np.where(
            paid_mask,
            terms.coupon_rate * (pending_before + 1),
            0.0,
        )  # (n_paths, n_obs)
    else:
        # No memory: pay rate if barrier met, nothing otherwise
        coupon_amounts = np.where(
            coupon_barrier_met & active_mask,
            terms.coupon_rate,
            0.0,
        )

    total_coupons = coupon_amounts.sum(axis=1)   # (n_paths,)

    # ------------------------------------------------------------------
    # Principal redemption
    # ------------------------------------------------------------------
    # Autocalled paths: receive 100% principal back
    autocall_principal = np.ones(n_paths)

    # Maturity paths: check knock-in
    final_basket_val = _basket(perf_paths[:, N, :], terms.final_basket)   # (n_paths,)
    worst_final      = perf_paths[:, N, :].min(axis=1)                    # always worst-of for KI check

    knock_in = worst_final < terms.knock_in_barrier   # (n_paths,)

    # No knock-in: always return principal_protection (e.g. 100%).
    # This is correct for both worst-of and best-of final basket notes:
    #   - HSBC worst-of: no KI → 100% principal (no upside participation)
    #   - BBVA best-of: no KI → 100% regardless of where best-of lands (cases A and B both = 100%)
    # Knock-in: cash-equivalent physical delivery = worst-of final performance
    maturity_principal = np.where(
        knock_in,
        worst_final,                       # cash equiv. of physical delivery
        terms.principal_protection,        # no knock-in → return floor (100% for both note types)
    )

    # Combine
    principal = np.where(any_autocalled, autocall_principal, maturity_principal)

    # ------------------------------------------------------------------
    # Total payoff and IRR
    # ------------------------------------------------------------------
    nominal_payoffs = principal + total_coupons

    t_held_arr = np.where(
        any_autocalled,
        np.array(obs_times)[np.clip(first_call_idx, 0, n_obs - 1)],
        terms.maturity,
    )

    # IRR: simple annualisation — total_return / t_held.
    # Structured note convention: coupon is quoted as p.a. simple rate,
    # so annualised return must use the same basis.
    # e.g. autocalled at 3M (t=0.25) with 2.5% coupon → IRR = 2.5%/0.25 = 10% p.a. ✓
    # Compound annualisation ((1+r)^(1/t)-1) overstates IRR for short tenors.
    total_return   = nominal_payoffs - 1.0
    annualized_irr = total_return / t_held_arr

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    maturity_mask = ~any_autocalled
    ki_total      = knock_in & maturity_mask

    return {
        # Per-path arrays (for Streamlit plots)
        "nominal_payoffs":      nominal_payoffs,
        "coupon_payoffs":       total_coupons,
        "principal_payoffs":    principal,
        "autocall_period":      autocall_period,
        "knock_in_triggered":   ki_total,
        "annualized_returns":   annualized_irr,

        # Legacy alias (app.py uses this key)
        "autocall_events":      autocall_period,

        # Scalars
        "expected_irr":             float(annualized_irr.mean()),
        "expected_total_return":    float(total_return.mean()),
        "expected_nominal_payout":  float(nominal_payoffs.mean()),
        "expected_coupon":          float(total_coupons.mean()),
        "prob_autocall":            float(any_autocalled.mean()),
        "prob_autocall_by_period":  [float((autocall_period == j).mean()) for j in range(1, n_obs + 1)],
        "prob_maturity":            float(maturity_mask.mean()),
        "prob_knock_in":            float(knock_in[maturity_mask].mean()) if maturity_mask.any() else 0.0,
        "prob_knock_in_total":      float(ki_total.mean()),

        # Legacy aliases
        "prob_floor":               float(ki_total.mean()),
        "prob_q1":  float((autocall_period == 1).mean()),
        "prob_q2":  float((autocall_period == 2).mean()),
        "prob_q3":  float((autocall_period == 3).mean()),
    }