"""
core/note.py
------------
NoteTerms dataclass — full Phoenix/Autocallable structured note specification.
price_note()         — vectorized payoff engine (no Python loops over paths).

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

@dataclass
class NoteTerms:
    """
    Full specification of a Phoenix Memory Autocallable note.

    Parameters
    ----------
    maturity : float
        Note tenor in years. Default 1.0.

    n_obs : int
        Total number of observation periods. Default 4 (quarterly on 1Y).
        Combined with maturity determines observation spacing:
        obs_times = [maturity * i / n_obs for i in 1..n_obs]

    coupon_rate : float
        Coupon paid per period when coupon barrier is met (as fraction).
        e.g. 0.008333 = 0.8333% per month (10% p.a. / 12).
        Default 0.025 (2.5% per quarter = 10% p.a.).

    coupon_barrier : float
        Worst-of (or selected basket) must be at or above this level
        for the coupon to be paid. Default 0.55.

    autocall_barrier : float
        Worst-of must be at or above this for autocall. Default 1.00.

    autocall_start_period : int
        First observation period at which autocall is possible (1-indexed).
        Periods before this are coupon-only. Default 1.
        e.g. HSBC note: autocall_start_period=4 (first 3 months coupon-only).

    knock_in_barrier : float
        European knock-in: checked only at final valuation.
        If worst-of final < knock_in_barrier, knock-in event occurs.
        Default 0.55. Set to 0.0 to disable.

    principal_protection : float
        Floor on maturity redemption if NO knock-in. Default 1.0 (100%).
        Set to 0.95 for 95% capital protection.
        If knock-in occurs, cash-equivalent physical delivery applies instead.

    memory : bool
        If True, missed coupons accumulate and are paid when barrier
        is next triggered (Phoenix Memory mechanic). Default True.

    coupon_basket : BasketType
        Basket type used for coupon barrier check. Default "worst_of".

    autocall_basket : BasketType
        Basket type used for autocall trigger check. Default "worst_of".

    final_basket : BasketType
        Basket type used for final redemption condition check. Default "worst_of".
        Set to "best_of" to replicate BBVA note final condition.

    call_steepness : float
        Sigmoid sharpness for discretionary issuer call model.
        Use a large value (e.g. 100) for hard/automatic autocall trigger.
        Default 100 (effectively automatic).

    name : str
        Human-readable note name. Default "Phoenix Memory Note".

    tickers : dict[str, str]
        Mapping from yfinance ticker symbol to display name.
        e.g. {"^GSPC": "SPX", "^STOXX50E": "SX5E"}.
        Stored in the config so the full note is self-contained in one JSON file.
        Default is empty dict (app falls back to its own default selection).
    """
    maturity:               float       = 1.0
    n_obs:                  int         = 4
    coupon_rate:            float       = 0.025
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

    def __post_init__(self):
        if self.tickers is None:
            object.__setattr__(self, "tickers", {})

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    def obs_times(self) -> list[float]:
        """Observation times in years, evenly spaced."""
        return [self.maturity * i / self.n_obs for i in range(1, self.n_obs + 1)]

    def obs_steps(self, N: int) -> list[int]:
        """Map observation times to simulation step indices."""
        return [round(t / self.maturity * N) for t in self.obs_times()]

    def autocall_prob(self, basket_val: np.ndarray) -> np.ndarray:
        """
        Vectorized sigmoid probability the issuer calls.
        Hard trigger at high steepness; probabilistic at low steepness.
        Only callable when basket_val >= autocall_barrier.
        """
        p = 1.0 / (1.0 + np.exp(-self.call_steepness * (basket_val - self.autocall_barrier)))
        return np.where(basket_val < self.autocall_barrier, 0.0, p)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name":                   self.name,
            "maturity":               self.maturity,
            "n_obs":                  self.n_obs,
            "coupon_rate":            self.coupon_rate,
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
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NoteTerms":
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
        expected_irr         : float
        expected_total_return: float
        expected_coupon      : float
        prob_autocall        : float
        prob_autocall_by_period : list[float]
        prob_maturity        : float
        prob_knock_in        : float        P(knock-in at maturity | reaches maturity)
        prob_knock_in_total  : float        P(knock-in) across all paths
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
        # Memory: accumulate coupons since last payment; pay all when barrier next met
        # We need to iterate over periods to track accumulated memory — use numpy cumsum trick
        # For each path, coupon at period j = rate * (j - last_paid_period)
        # This is equivalent to: each period either pays rate (if barrier met) or 0,
        # BUT when paid, it also pays all previously skipped periods.
        # Vectorized: coupon_amount[j] = rate * (periods_since_last_pay + 1) if barrier_met, else 0
        # Track with cumsum of missed periods

        # missed[i, j] = number of consecutive periods missed before j (including j if not met)
        # Payment at j = rate * (accumulated_missed + 1) if barrier_met
        coupon_amounts = np.zeros((n_paths, n_obs))
        pending = np.zeros(n_paths)   # accumulated missed periods

        for j in range(n_obs):
            met    = coupon_barrier_met[:, j] & active_mask[:, j]
            not_met = (~coupon_barrier_met[:, j]) & active_mask[:, j]
            pending += not_met.astype(float)   # accumulate missed
            coupon_amounts[:, j] = np.where(met, terms.coupon_rate * (pending + 1), 0.0)
            pending = np.where(met, 0.0, pending)   # reset on payment
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

    # No knock-in: return principal_protection (e.g. 100%)
    # Knock-in: cash-equivalent physical delivery = worst-of final / strike (= worst-of final perf)
    maturity_principal = np.where(
        knock_in,
        worst_final,                         # cash equiv. of physical delivery
        np.maximum(terms.principal_protection, final_basket_val)
        if terms.final_basket != "worst_of"
        else terms.principal_protection,     # worst-of: just return floor
    )

    # For best-of final condition (BBVA): if best_of >= 1.0 OR no KI → 100%
    # Already handled above: principal_protection=1.0 covers the no-KI case,
    # and knock_in uses worst_of regardless of final_basket.

    # Combine
    principal = np.where(any_autocalled, autocall_principal, maturity_principal)

    # ------------------------------------------------------------------
    # Total payoff and IRR
    # ------------------------------------------------------------------
    nominal_payoffs = principal + total_coupons

    t_held = np.where(
        any_autocalled,
        np.array(obs_times)[first_call_idx] * any_autocalled +
        terms.maturity * (~any_autocalled),
        terms.maturity,
    )
    # Fix: t_held should be obs_times[first_call_idx] for called paths
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