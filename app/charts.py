"""
app/charts.py
-------------
Every Plotly figure in the app as a standalone function.

All functions:
- take plain numpy / pandas arguments
- return a plotly.graph_objects.Figure
- accept a Translator instance for axis/legend labels
- have no Streamlit calls — tested independently

Usage
-----
from app.charts import (
    build_irr_distribution,
    build_fan_chart, build_wof_fan, build_corr_heatmap,
    build_backtest_irr_scatter, build_backtest_outcome_bar,
    build_worst_asset_pie, build_historical_prices, build_historical_wof_path,
    build_live_performance_chart,
)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from translations import Translator

# Consistent colour palette
_GREEN_DARK   = "#145214"
_GREEN_MID    = "#1a6b1a"
_GREEN_LIGHT  = "#2ecc71"
_RED          = "#c0392b"
_GREY         = "#888888"
_WHITE        = "white"

def _add_autocall_barrier(fig: go.Figure, autocall_barrier, autocall_schedule) -> None:
    """
    Draw the autocall barrier on a performance chart.

    If `autocall_schedule` (a list of (time, level) points) is given and the
    levels actually vary, draw a stepped dotted line that follows the step-down
    schedule. Otherwise fall back to a single flat dotted line at
    `autocall_barrier`. No-op when neither is supplied.
    """
    if autocall_schedule and len({round(lvl, 6) for _, lvl in autocall_schedule}) > 1:
        xs = [0.0] + [t for t, _ in autocall_schedule]
        ys = [autocall_schedule[0][1]] + [lvl for _, lvl in autocall_schedule]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color=_GREY, dash="dot", width=1.5, shape="hv"),
            name="Autocall barrier", hovertemplate="Autocall barrier: %{y:.0%}<extra></extra>",
        ))
    elif autocall_barrier is not None:
        fig.add_hline(
            y=autocall_barrier, line_dash="dot", line_color=_GREY,
            annotation_text=f"Autocall barrier ({autocall_barrier:.0%})",
            annotation_position="top right",
        )


def _plain_layout(fig: go.Figure) -> go.Figure:
    fig.update_layout(plot_bgcolor=_WHITE, paper_bgcolor=_WHITE)
    return fig


def _add_coupon_barrier(fig: go.Figure, coupon_barrier: float,
                        knock_in_barrier: float) -> None:
    """
    Draw the coupon barrier as its own orange dashed line when it is distinct
    from the KI barrier and not a guaranteed coupon (level 0). Never relabel
    the KI line as a coupon barrier — they are different term-sheet levels.
    """
    if coupon_barrier and abs(coupon_barrier - knock_in_barrier) > 1e-9:
        fig.add_hline(
            y=coupon_barrier, line_dash="dash", line_color="#e67e22",
            annotation_text=f"Coupon barrier ({coupon_barrier:.1%})",
            annotation_position="bottom left",
        )


# ---------------------------------------------------------------------------
# Tab 1 — IRR distribution
# ---------------------------------------------------------------------------

def build_irr_distribution(
    annualized_returns: np.ndarray,
    autocall_events:    np.ndarray,
    expected_irr:       float,
    coupon_rate_pa:     float,      # p.a. coupon for reference line
    tr:                 Translator,
) -> go.Figure:
    """
    Histogram of annualised IRR across all paths.
    Both traces share the same bin edges and are normalised over the TOTAL
    path count so bar heights are comparable (i.e. they add up to 100%).
    """
    irr_all      = annualized_returns
    irr_called   = irr_all[autocall_events > 0]
    irr_maturity = irr_all[autocall_events == 0]
    n_total      = len(irr_all)

    # Shared bin edges computed from the full distribution.
    # Bins span the 1st–99th percentile so they aren't wasted on extreme
    # outliers; values beyond that are CLIPPED into the edge bins (not
    # dropped) so the bars genuinely sum to 100% of paths.
    lo = float(np.percentile(irr_all, 1))
    hi = float(np.percentile(irr_all, 99))
    if hi <= lo:                      # degenerate distribution guard
        lo, hi = lo - 0.01, hi + 0.01
    n_bins = 60
    bin_size = (hi - lo) / n_bins
    irr_called   = np.clip(irr_called,   lo, hi)
    irr_maturity = np.clip(irr_maturity, lo, hi)

    fig = go.Figure()

    if len(irr_called) > 0:
        # Weight each count by 1/n_total so both traces share the same probability axis
        counts_c, edges = np.histogram(irr_called, bins=np.linspace(lo, hi, n_bins + 1))
        fig.add_trace(go.Bar(
            x=edges[:-1] + bin_size / 2,
            y=counts_c / n_total,
            width=bin_size * 0.95,
            name=f"Autocalled ({len(irr_called)/n_total:.0%})",
            marker_color=_GREEN_LIGHT,
            opacity=0.85,
        ))

    if len(irr_maturity) > 0:
        counts_m, edges = np.histogram(irr_maturity, bins=np.linspace(lo, hi, n_bins + 1))
        fig.add_trace(go.Bar(
            x=edges[:-1] + bin_size / 2,
            y=counts_m / n_total,
            width=bin_size * 0.95,
            name=f"Maturity ({len(irr_maturity)/n_total:.0%})",
            marker_color=_GREEN_DARK,
            opacity=0.75,
        ))

    # Reference lines — stagger annotation positions to avoid overlap
    fig.add_vline(
        x=expected_irr, line_dash="dash", line_color=_GREEN_MID, line_width=1.5,
        annotation_text=f"Mean {expected_irr:.2%}",
        annotation_position="top right",
        annotation_font_size=11,
    )
    fig.add_vline(
        x=coupon_rate_pa, line_dash="dot", line_color=_GREY, line_width=1.5,
        annotation_text=f"Coupon {coupon_rate_pa:.2%} p.a.",
        annotation_position="top left",
        annotation_font_size=11,
    )
    fig.add_vline(
        x=0, line_dash="solid", line_color=_RED, line_width=1,
        annotation_text="0%",
        annotation_position="bottom right",
        annotation_font_size=10,
    )

    fig.update_layout(
        title="Annualised IRR Distribution — All Simulated Paths",
        xaxis=dict(title="Annualised IRR (simple)", tickformat=".0%"),
        yaxis=dict(title="Share of all paths", tickformat=".1%"),
        barmode="overlay",
        legend=dict(x=0.01, y=0.99),
        hovermode="x unified",
        bargap=0,
    )
    return _plain_layout(fig)


# ---------------------------------------------------------------------------
# Tab 2 — per-asset fan chart
# ---------------------------------------------------------------------------

def build_fan_chart(
    paths:      np.ndarray,   # (n_paths, N+1) — single asset
    asset_name: str,
    t_grid:     np.ndarray,
    obs_labels: list[tuple[str, float]],  # [(label, t), ...] e.g. [("3M", 0.25)]
    tr:         Translator,
) -> go.Figure:
    S0 = paths[:, 0].mean()
    pcts = [5, 25, 50, 75, 95]
    bands = np.percentile(paths, pcts, axis=0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[4], bands[0][::-1]]),
        fill="toself", fillcolor="rgba(26,107,26,0.08)",
        line=dict(color="rgba(0,0,0,0)"),
        name=tr("pct_5_95"),
    ))
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[3], bands[1][::-1]]),
        fill="toself", fillcolor="rgba(26,107,26,0.20)",
        line=dict(color="rgba(0,0,0,0)"),
        name=tr("pct_25_75"),
    ))
    fig.add_trace(go.Scatter(
        x=t_grid, y=bands[2],
        mode="lines", name=tr("median"),
        line=dict(color=_GREEN_MID, width=2),
    ))
    fig.add_hline(y=S0, line_dash="dash", line_color=_GREY,
                  annotation_text="S₀", annotation_position="right")

    for label, t_val in obs_labels:
        fig.add_vline(x=t_val, line_dash="dot", line_color="#aaa",
                      annotation_text=label, annotation_position="top")

    fig.update_layout(
        title=f"{asset_name} — {tr('simulated_price_dist')}",
        xaxis=dict(title=tr("time_years"), tickformat=".2f"),
        yaxis=dict(title=tr("price")),
        hovermode="x unified",
        legend=dict(x=0.01, y=0.99),
    )
    return _plain_layout(fig)


# ---------------------------------------------------------------------------
# Tab 2 — worst-of fan chart
# ---------------------------------------------------------------------------

def build_wof_fan(
    worst_of_paths:   np.ndarray,
    t_grid:           np.ndarray,
    knock_in_barrier: float,
    obs_labels:       list[tuple[str, float]],
    tr:               Translator,
    autocall_barrier: float | None = None,
    autocall_schedule: list[tuple[float, float]] | None = None,
) -> go.Figure:
    pcts = [5, 25, 50, 75, 95]
    bands = np.percentile(worst_of_paths, pcts, axis=0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[4], bands[0][::-1]]),
        fill="toself", fillcolor="rgba(26,107,26,0.08)",
        line=dict(color="rgba(0,0,0,0)"), name=tr("pct_5_95"),
    ))
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[3], bands[1][::-1]]),
        fill="toself", fillcolor="rgba(26,107,26,0.20)",
        line=dict(color="rgba(0,0,0,0)"), name=tr("pct_25_75"),
    ))
    fig.add_trace(go.Scatter(
        x=t_grid, y=bands[2],
        mode="lines", name=tr("median"),
        line=dict(color=_GREEN_MID, width=2),
    ))
    fig.add_hline(
        y=knock_in_barrier, line_dash="dash", line_color=_RED,
        annotation_text=f"Knock-in barrier ({knock_in_barrier:.0%})",
        annotation_position="bottom right",
    )
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule)
    for label, t_val in obs_labels:
        fig.add_vline(x=t_val, line_dash="dot", line_color="#aaa",
                      annotation_text=label, annotation_position="top")

    fig.update_layout(
        xaxis=dict(title=tr("time_years"), tickformat=".2f"),
        yaxis=dict(title=tr("perf_vs_initial"), tickformat=".0%"),
        hovermode="x unified",
        legend=dict(x=0.01, y=0.01),
    )
    return _plain_layout(fig)


# ---------------------------------------------------------------------------
# Tab 3 — path explorer: price paths
# ---------------------------------------------------------------------------

def build_path_price_chart(
    path_prices: pd.DataFrame,
    path_num:    int,
    obs_steps:   list[int],
    obs_labels:  list[str],
    tr:          Translator,
) -> go.Figure:
    fig = px.line(
        path_prices,
        title=tr("asset_price_paths", n=path_num),
        labels={
            "value": tr("price_label"),
            "index": tr("time_step"),
        },
        color_discrete_sequence=[_GREEN_MID, _GREEN_LIGHT, _GREEN_DARK],
    )
    for step, label in zip(obs_steps, obs_labels):
        fig.add_vline(x=step, line_dash="dot", line_color="#aaa",
                      annotation_text=label, annotation_position="top")
    return _plain_layout(fig)


def build_path_wof_chart(
    worst_path:       np.ndarray,
    autocall_q:       int,
    obs_steps:        list[int],
    obs_labels:       list[str],
    knock_in_barrier: float,
    path_num:         int,
    tr:               Translator,
    asset_paths:      np.ndarray | None = None,
    asset_names:      list[str]  | None = None,
    autocall_barrier: float | None      = None,
    autocall_schedule: list[tuple[float, float]] | None = None,
) -> go.Figure:
    asset_colors = [_GREEN_MID, _GREEN_LIGHT, _GREEN_DARK, "#f39c12", "#9b59b6"]
    fig = go.Figure()

    # Per-asset lines behind worst-of (if provided)
    if asset_paths is not None and asset_names is not None:
        for i, name in enumerate(asset_names):
            fig.add_trace(go.Scatter(
                y=asset_paths[:, i], mode="lines", name=name,
                line=dict(color=asset_colors[i % len(asset_colors)], width=1.2, dash="dot"),
                opacity=0.65,
            ))

    fig.add_trace(go.Scatter(
        y=worst_path, mode="lines",
        name="Worst-of",
        line=dict(color=_GREEN_DARK, width=2.5),
    ))
    fig.add_hline(
        y=knock_in_barrier, line_dash="dash", line_color=_RED,
        annotation_text=f"Knock-in barrier ({knock_in_barrier:.0%})",
        annotation_position="bottom right",
    )
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule)
    for i, (step, label) in enumerate(zip(obs_steps, obs_labels)):
        called_here  = (autocall_q == i + 1)
        marker_color = _GREEN_MID if called_here else _GREY
        marker_sym   = "star"     if called_here else "circle"
        suffix       = tr("called_label") if called_here else tr("continued_label")
        fig.add_trace(go.Scatter(
            x=[step], y=[worst_path[step]],
            mode="markers",
            marker=dict(size=12, color=marker_color, symbol=marker_sym),
            name=f"{label} {suffix}",
        ))
        fig.add_vline(x=step, line_dash="dot", line_color="#aaa",
                      annotation_text=label, annotation_position="top")

    fig.update_layout(
        title=tr("wof_path_title", n=path_num),
        yaxis=dict(title=tr("perf_vs_initial"), tickformat=".0%"),
        xaxis=dict(title=tr("time_step")),
        hovermode="x unified",
    )
    return _plain_layout(fig)


# ---------------------------------------------------------------------------
# Tab 4 — correlation heatmaps
# ---------------------------------------------------------------------------

def build_corr_heatmap(
    matrix:     np.ndarray,
    asset_names: list[str],
    title:      str,
    zmin:       float = -1.0,
    zmax:       float =  1.0,
) -> go.Figure:
    df = pd.DataFrame(matrix, index=asset_names, columns=asset_names)
    fig = px.imshow(
        df, text_auto=".3f",
        color_continuous_scale=[[0, _RED], [0.5, _WHITE], [1, _GREEN_MID]],
        zmin=zmin, zmax=zmax,
        title=title, aspect="auto",
    )
    fig.update_layout(coloraxis_showscale=False, paper_bgcolor=_WHITE)
    return fig


# ---------------------------------------------------------------------------
# Backtest — outcome bar chart
# ---------------------------------------------------------------------------

def build_backtest_outcome_bar(
    bt:         pd.DataFrame,
    color_map:  dict[str, str],
    tr:         Translator,
) -> go.Figure:
    outcome_counts = bt["Outcome"].value_counts().reset_index()
    outcome_counts.columns = ["Outcome", tr("count")]
    fig = px.bar(
        outcome_counts,
        x="Outcome", y=tr("count"),
        color="Outcome",
        color_discrete_map=color_map,
        title=tr("outcome_dist"),
        text=tr("count"),
    )
    fig.update_layout(showlegend=False)
    return _plain_layout(fig)


# ---------------------------------------------------------------------------
# Backtest — worst asset pie
# ---------------------------------------------------------------------------

def build_worst_asset_pie(
    bt:  pd.DataFrame,
    tr:  Translator,
) -> go.Figure:
    # Primary: worst asset at maturity (knock-in risk context)
    maturity_bt = bt[bt["Call Quarter"] == 0]
    if not maturity_bt.empty:
        wc    = maturity_bt["Worst Asset"].value_counts().reset_index()
        title = tr("worst_asset_at_mat")
    else:
        # All paths autocalled — show worst asset at call date instead
        wc    = bt["Worst Asset"].value_counts().reset_index()
        title = "Worst Asset at Call Date"

    if wc.empty:
        return go.Figure()

    wc.columns = [tr("asset"), tr("count")]
    fig = px.pie(
        wc,
        names=tr("asset"),
        values=tr("count"),
        title=title,
        hole=0.4,
        color_discrete_sequence=[_GREEN_MID, _GREEN_LIGHT, _GREEN_DARK],
    )
    fig.update_layout(paper_bgcolor=_WHITE)
    return fig


# ---------------------------------------------------------------------------
# Backtest — IRR scatter by issue date
# ---------------------------------------------------------------------------

def build_backtest_irr_scatter(
    bt:        pd.DataFrame,
    color_map: dict[str, str],
    tr:        Translator,
) -> go.Figure:
    fig = px.scatter(
        bt, x="Issue Date", y="IRR", color="Outcome",
        color_discrete_map=color_map,
        hover_data=["Payout", "Worst Asset", "Worst Final Perf"],
        title=tr("realised_irr_title"),
    )
    fig.add_hline(
        y=0, line_dash="dash", line_color=_GREY,
        annotation_text=tr("break_even"),
        annotation_position="right",
    )
    fig.update_layout(yaxis=dict(tickformat=".1%"))
    return _plain_layout(fig)


# ---------------------------------------------------------------------------
# Backtest — historical normalised price paths
# ---------------------------------------------------------------------------

def build_historical_prices(
    hist_prices:  pd.DataFrame,
    bt_start:     pd.Timestamp,
    bt_end:       pd.Timestamp,
    tr:           Translator,
) -> go.Figure:
    palette = [_GREEN_MID, _GREEN_LIGHT, _GREEN_DARK, "#f39c12", "#9b59b6"]
    fig = go.Figure()
    for i, col in enumerate(hist_prices.columns):
        normed = hist_prices[col] / hist_prices[col].iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=hist_prices.index, y=normed,
            mode="lines", name=col,
            line=dict(color=palette[i % len(palette)], width=1.5),
        ))
    fig.add_vline(x=bt_start.isoformat(), line_dash="dot", line_color=_GREY,
                  annotation_text=tr("backtest_start"), annotation_position="top right")
    fig.add_vline(x=bt_end.isoformat(),   line_dash="dot", line_color=_GREY,
                  annotation_text=tr("backtest_end"),   annotation_position="top left")
    fig.update_layout(
        xaxis=dict(title=tr("date_axis")),
        yaxis=dict(title=tr("normalised_level")),
        hovermode="x unified",
        legend=dict(x=0.01, y=0.99),
    )
    return _plain_layout(fig)


# ---------------------------------------------------------------------------
# Backtest — historical worst-of performance path for a specific issue date
# ---------------------------------------------------------------------------

def build_historical_wof_path(
    hist_prices:      pd.DataFrame,
    issue_date:       pd.Timestamp,
    obs_dates:        list[pd.Timestamp],
    knock_in_barrier: float,
    autocall_barrier: float,
    coupon_barrier:   float,
    call_quarter:     int,
    tr:               Translator,
    autocall_schedule: list[tuple] | None = None,
    coupon_at_autocall_only: bool = False,
) -> go.Figure:
    """
    Show per-asset performance + worst-of line for one historical issue date.

    obs_dates are the SNAPPED trading-day observation dates (the same ones the
    payoff engine evaluated). Markers stop at the autocall date — the note no
    longer exists afterwards. The coupon barrier colours the markers and is
    drawn as its own line when it differs from the KI barrier (never conflate
    the two). For step-down notes pass autocall_schedule = [(date, level),...].
    """
    issue_idx = hist_prices.index.searchsorted(issue_date)
    if obs_dates:
        end_idx = min(int(hist_prices.index.searchsorted(obs_dates[-1])) + 1, len(hist_prices))
    else:
        end_idx = len(hist_prices)
    slice_    = hist_prices.iloc[issue_idx:end_idx]
    dates     = slice_.index
    S0        = hist_prices.iloc[issue_idx].values.astype(float)

    # Normalise each asset to 1.0 at issue date
    perf = slice_.values / S0[np.newaxis, :]    # (days, n_assets)
    wof  = perf.min(axis=1)

    asset_colors = [_GREEN_MID, _GREEN_LIGHT, _GREEN_DARK, "#f39c12", "#9b59b6"]
    asset_names  = list(hist_prices.columns)

    fig = go.Figure()

    # Per-asset lines (lighter, dashed)
    for i, name in enumerate(asset_names):
        fig.add_trace(go.Scatter(
            x=dates, y=perf[:, i],
            mode="lines", name=name,
            line=dict(color=asset_colors[i % len(asset_colors)], width=1.2, dash="dot"),
            opacity=0.65,
        ))

    # Worst-of line (solid, prominent)
    fig.add_trace(go.Scatter(
        x=dates, y=wof,
        mode="lines", name="Worst-of",
        line=dict(color=_GREEN_DARK, width=2.5),
    ))

    # Barriers — KI, coupon (when distinct), and autocall (flat or stepped)
    fig.add_hline(y=knock_in_barrier, line_dash="dash", line_color=_RED,
                  annotation_text=f"Knock-in barrier ({knock_in_barrier:.1%})",
                  annotation_position="bottom right")
    _add_coupon_barrier(fig, coupon_barrier, knock_in_barrier)
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule)

    # Observation markers — only while the note is alive
    for q, obs_date in enumerate(obs_dates):
        loc = hist_prices.index.searchsorted(obs_date) - issue_idx
        if loc < 0 or loc >= len(dates):
            break
        wof_val = float(wof[loc])
        is_call = (call_quarter == q + 1)
        if coupon_at_autocall_only:
            # No periodic coupon — colour by the call, not a coupon barrier
            color = _GREEN_MID if is_call else _GREY
        else:
            color = _GREEN_MID if wof_val >= coupon_barrier else _RED
        symbol  = "star" if is_call else "circle"
        size    = 14 if is_call else 9
        label   = f"P{q+1} {'← CALLED' if is_call else ''}"

        fig.add_trace(go.Scatter(
            x=[obs_date], y=[wof_val],
            mode="markers",
            marker=dict(size=size, color=color, symbol=symbol,
                        line=dict(width=1.5, color="white")),
            name=label, showlegend=True,
        ))
        fig.add_vline(x=obs_date.isoformat(), line_dash="dot",
                      line_color="#cccccc",
                      annotation_text=f"P{q+1}", annotation_position="top")
        if is_call:
            break   # the note terminated here — later observations never happen

    outcome = "Autocalled" if call_quarter > 0 else "Maturity"
    fig.update_layout(
        title=f"Historical Worst-of Path — Issue: {issue_date.date()} · Outcome: {outcome} P{call_quarter}" if call_quarter > 0
              else f"Historical Worst-of Path — Issue: {issue_date.date()} · Outcome: Maturity",
        xaxis=dict(title="Date"),
        yaxis=dict(title="Performance vs Issue Date", tickformat=".0%"),
        hovermode="x unified",
        legend=dict(x=1.01, y=1, xanchor="left"),
    )
    return _plain_layout(fig)

# ---------------------------------------------------------------------------
# Current Note Performance (live — from issue date to today)
# ---------------------------------------------------------------------------

def build_live_performance_chart(
    hist_prices:        pd.DataFrame,   # prices from issue_date to today
    issue_date:         pd.Timestamp,
    today:              pd.Timestamp,
    maturity_date:      pd.Timestamp,
    obs_markers:        list[dict],     # precomputed by core.note.replay_note via app
    future_obs:         list[tuple],    # [(label, calendar_date), ...] still to come
    knock_in_barrier:   float,
    autocall_barrier:   float,
    coupon_barrier:     float,
    tr:                 "Translator",
    autocall_schedule:  list[tuple] | None = None,
) -> go.Figure:
    """
    Live performance chart from issue date to today.

    This function only DRAWS — all payoff logic (memory coupons, step-down
    autocall schedule, coupon_at_autocall_only) is computed once in
    core.note.replay_note and passed in via obs_markers:
        {"date", "label", "wof", "autocalled", "paid", "amount"}
    Future observation dates arrive as faint reference lines via future_obs.
    """
    issue_idx = hist_prices.index.searchsorted(issue_date)
    S0 = hist_prices.iloc[issue_idx].values.astype(float)

    slice_ = hist_prices.iloc[issue_idx:]
    dates  = slice_.index
    perf   = slice_.values / S0[np.newaxis, :]
    wof    = perf.min(axis=1)

    asset_colors = [_GREEN_MID, _GREEN_LIGHT, _GREEN_DARK, "#f39c12", "#9b59b6"]
    asset_names  = list(hist_prices.columns)

    fig = go.Figure()

    # Per-asset lines
    for i, name in enumerate(asset_names):
        fig.add_trace(go.Scatter(
            x=dates, y=perf[:, i],
            mode="lines", name=name,
            line=dict(color=asset_colors[i % len(asset_colors)], width=1.2, dash="dot"),
            opacity=0.65,
        ))

    # Worst-of line
    fig.add_trace(go.Scatter(
        x=dates, y=wof,
        mode="lines", name="Worst-of",
        line=dict(color=_GREEN_DARK, width=2.5),
    ))

    # Barriers — KI, coupon (when distinct), and autocall (flat or stepped)
    fig.add_hline(y=knock_in_barrier, line_dash="dash", line_color=_RED,
                  annotation_text=f"Knock-in barrier ({knock_in_barrier:.1%})",
                  annotation_position="bottom right")
    _add_coupon_barrier(fig, coupon_barrier, knock_in_barrier)
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule)

    # Today line
    if today in dates or today >= dates[0]:
        fig.add_vline(x=today.isoformat(), line_dash="solid", line_color="#2c3e50",
                      line_width=2,
                      annotation_text="Today", annotation_position="top left")

    # Past observation markers (status precomputed by replay_note)
    for m in obs_markers:
        if m["autocalled"]:
            tip = f"{m['label']}: AUTOCALLED" + (
                f" · Premium {m['amount']:.4%}" if m["amount"] > 0 else "")
            color, symbol, size = _GREEN_MID, "star", 12
        elif m["paid"]:
            tip = f"{m['label']}: Coupon {m['amount']:.4%}"
            color, symbol, size = _GREEN_MID, "circle", 9
        else:
            tip = f"{m['label']}: Coupon missed"
            color, symbol, size = _RED, "circle", 9
        fig.add_trace(go.Scatter(
            x=[m["date"]], y=[m["wof"]],
            mode="markers",
            marker=dict(size=size, color=color, symbol=symbol,
                        line=dict(width=1.5, color="white")),
            name=tip, showlegend=True,
            hovertemplate=f"{tip}<br>Worst-of: {m['wof']:.1%}<extra></extra>",
        ))
        fig.add_vline(x=m["date"].isoformat(), line_dash="dot", line_color="#cccccc",
                      annotation_text=m["label"], annotation_position="top")

    # Future observation reference lines (calendar dates)
    for label, obs_date in future_obs:
        if pd.Timestamp(obs_date) <= maturity_date:
            fig.add_vline(x=pd.Timestamp(obs_date).isoformat(), line_dash="dot",
                          line_color="#dddddd",
                          annotation_text=label, annotation_position="top")

    fig.update_layout(
        title=f"Live Performance — Issue: {issue_date.date()} · Maturity: {maturity_date.date()}",
        xaxis=dict(title="Date"),
        yaxis=dict(title="Performance vs Issue Date", tickformat=".0%"),
        hovermode="x unified",
        legend=dict(x=1.01, y=1, xanchor="left"),
    )
    return _plain_layout(fig)