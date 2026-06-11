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

# ---------------------------------------------------------------------------
# Institutional palette — navy / blue, matching the PDF report and web theme.
# The historical names (_GREEN_*) are kept so every existing call site keeps
# working; only the colour values change.
# ---------------------------------------------------------------------------
_NAVY         = "#1a2e4a"   # primary / worst-of line / dark series
_BLUE         = "#2563eb"   # accent / median / primary series
_BLUE_LIGHT   = "#60a5fa"   # light blue secondary series
_GREEN_DARK   = _NAVY       # alias: darkest series
_GREEN_MID    = _BLUE       # alias: primary series / median
_GREEN_LIGHT  = _BLUE_LIGHT # alias: secondary series
_RED          = "#dc2626"   # barrier / loss / negative
_GREY         = "#6b7280"   # warm grey — secondary lines/text
_WHITE        = "white"

# Extra categorical colours for multi-asset charts (>3 underlyings)
_SERIES_COLORS = [_BLUE, _NAVY, _BLUE_LIGHT, "#0891b2", "#7c3aed", "#0d9488"]

_BASE_FONT = "IBM Plex Sans, Arial, sans-serif"

# Light fill tints for fan-chart bands (blue, low alpha)
_FILL_OUTER = "rgba(37,99,235,0.08)"
_FILL_INNER = "rgba(37,99,235,0.20)"


def _apply_theme(fig: go.Figure) -> go.Figure:
    """
    Shared clean theme for every figure: white background, IBM Plex Sans font,
    navy text, light-grey gridlines, no Plotly logo. Preserves all existing
    traces, barrier lines, markers and titles.
    """
    fig.update_layout(
        plot_bgcolor=_WHITE,
        paper_bgcolor=_WHITE,
        font=dict(family=_BASE_FONT, size=12, color=_NAVY),
        title=dict(font=dict(family=_BASE_FONT, size=15, color=_NAVY)),
        legend=dict(
            font=dict(family=_BASE_FONT, size=11, color=_NAVY),
            bgcolor="rgba(255,255,255,0.6)",
            bordercolor="#e5e7eb", borderwidth=0,
        ),
        margin=dict(l=60, r=30, t=50, b=50),
        modebar_remove=["logo", "sendDataToCloud", "lasso2d", "select2d"],
        colorway=_SERIES_COLORS,
    )
    fig.update_xaxes(
        linecolor="#e5e7eb", gridcolor="#f1f5f9", zerolinecolor="#e5e7eb",
        title_font=dict(family=_BASE_FONT, size=12, color=_GREY),
        tickfont=dict(family=_BASE_FONT, size=11, color=_GREY),
    )
    fig.update_yaxes(
        linecolor="#e5e7eb", gridcolor="#f1f5f9", zerolinecolor="#e5e7eb",
        title_font=dict(family=_BASE_FONT, size=12, color=_GREY),
        tickfont=dict(family=_BASE_FONT, size=11, color=_GREY),
    )
    # The title font set above creates a title object; if a chart never set
    # title text, plotly.js renders the literal JS value "undefined" as the
    # title. Blank it so title-less charts show nothing instead of "undefined".
    if fig.layout.title.text is None:
        fig.update_layout(title_text="")
    return fig

def _add_autocall_barrier(fig: go.Figure, autocall_barrier, autocall_schedule,
                          tr: Translator, x0=None) -> None:
    """
    Draw the autocall barrier on a performance chart.

    If `autocall_schedule` (a list of (x, level) points) is given and the
    levels actually vary, draw a stepped dotted line that follows the step-down
    schedule. Otherwise fall back to a single flat dotted line at
    `autocall_barrier`. No-op when neither is supplied.

    x0 is the chart origin the stepped line starts from (0.0 for time/step
    axes, the ISSUE DATE for date axes). It must match the axis type of the
    schedule's x values — defaulting a date axis to 0.0 would anchor the line
    at the Unix epoch (Jan 1970) and blow up the x-range.
    """
    if autocall_schedule and len({round(lvl, 6) for _, lvl in autocall_schedule}) > 1:
        if x0 is None:
            x0 = autocall_schedule[0][0]
        xs = [x0] + [t for t, _ in autocall_schedule]
        ys = [autocall_schedule[0][1]] + [lvl for _, lvl in autocall_schedule]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color=_GREY, dash="dot", width=1.5, shape="hv"),
            name=tr("chart_autocall_barrier"),
            hovertemplate=f"{tr('chart_autocall_barrier')}: %{{y:.0%}}<extra></extra>",
        ))
    elif autocall_barrier is not None:
        fig.add_hline(
            y=autocall_barrier, line_dash="dot", line_color=_GREY,
            annotation_text=tr("chart_autocall_barrier_lvl", lvl=f"{autocall_barrier:.0%}"),
            annotation_position="top right",
        )


def _plain_layout(fig: go.Figure) -> go.Figure:
    return _apply_theme(fig)


def _add_coupon_barrier(fig: go.Figure, coupon_barrier: float,
                        knock_in_barrier: float, tr: Translator) -> None:
    """
    Draw the coupon barrier as its own orange dashed line when it is distinct
    from the KI barrier and not a guaranteed coupon (level 0). Never relabel
    the KI line as a coupon barrier — they are different term-sheet levels.
    """
    if coupon_barrier and abs(coupon_barrier - knock_in_barrier) > 1e-9:
        fig.add_hline(
            y=coupon_barrier, line_dash="dash", line_color="#e67e22",
            annotation_text=tr("chart_coupon_barrier_lvl", lvl=f"{coupon_barrier:.1%}"),
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

    # ── Adaptive bin edges + zoom window ───────────────────────────────
    # The distribution can be extremely narrow and concentrated (e.g. a note
    # that autocalls ~84% of the time clusters almost all mass at one IRR, with
    # a thin loss tail reaching far to the left). Binning over the full
    # min..max range then wastes nearly every bin and crams all bars at one
    # edge, and the x-axis spans a useless -50%..+10%.
    #
    # Fix: choose a ROBUST inner window from percentiles of the data (so the
    # concentrated bulk fills the plot), build adaptive-width bins over that
    # window, and CLIP outliers into the edge bins (so the thin loss tail still
    # shows as a small edge bar — nothing is dropped and bars sum to 100%).
    lo_data = float(np.min(irr_all))

    # Robust window: 2nd–98th percentile captures the bulk while trimming the
    # extreme tail that would otherwise dominate the axis.
    p_lo = float(np.percentile(irr_all, 2))
    p_hi = float(np.percentile(irr_all, 98))
    # Always keep 0% and the reference markers in view when they're nearby.
    lo_w = min(p_lo, 0.0, expected_irr, coupon_rate_pa)
    hi_w = max(p_hi, expected_irr, coupon_rate_pa)
    span = hi_w - lo_w
    if span <= 1e-9:                      # fully degenerate (all identical)
        lo_w, hi_w = lo_w - 0.01, hi_w + 0.01
        span = hi_w - lo_w
    pad = span * 0.05
    lo_e, hi_e = lo_w - pad, hi_w + pad

    # Adaptive bin count from the data spread inside the window, clamped so we
    # never get 1–2 bins (unreadable) or hundreds.
    try:
        inner = irr_all[(irr_all >= lo_w) & (irr_all <= hi_w)]
        auto_edges = np.histogram_bin_edges(inner if inner.size > 1 else irr_all, bins="auto")
        n_bins = len(auto_edges) - 1
    except Exception:
        n_bins = 40
    n_bins = int(np.clip(n_bins, 25, 80))

    edges    = np.linspace(lo_e, hi_e, n_bins + 1)
    bin_size = (hi_e - lo_e) / n_bins

    # Clip into the window so tail paths land in the edge bins (counted, not lost)
    irr_called_c   = np.clip(irr_called,   lo_e, hi_e)
    irr_maturity_c = np.clip(irr_maturity, lo_e, hi_e)

    fig = go.Figure()

    if len(irr_called_c) > 0:
        # Weight each count by 1/n_total so both traces share the same probability axis
        counts_c, _ = np.histogram(irr_called_c, bins=edges)
        fig.add_trace(go.Bar(
            x=edges[:-1] + bin_size / 2,
            y=counts_c / n_total,
            width=bin_size * 0.95,
            name=tr("chart_legend_autocalled", pct=f"{len(irr_called)/n_total:.0%}"),
            marker_color=_GREEN_LIGHT,
            opacity=0.85,
        ))

    if len(irr_maturity_c) > 0:
        counts_m, _ = np.histogram(irr_maturity_c, bins=edges)
        fig.add_trace(go.Bar(
            x=edges[:-1] + bin_size / 2,
            y=counts_m / n_total,
            width=bin_size * 0.95,
            name=tr("chart_legend_maturity", pct=f"{len(irr_maturity)/n_total:.0%}"),
            marker_color=_GREEN_DARK,
            opacity=0.75,
        ))

    # X-axis zooms to the robust window. Flag a clipped loss tail in the subtitle.
    # Extra right-hand headroom so the Mean/Coupon labels (which can sit near the
    # right edge for a high-autocall note) have room and never get clipped.
    x_range = [lo_e, hi_e + span * 0.10]
    _clip_note = (tr("chart_irr_clip_note", lvl=f"{lo_data:.0%}")
                  if lo_data < lo_e - 1e-9 else "")

    # ── Reference lines — stagger labels so they never collide ─────────
    # Mean and Coupon can sit almost on top of each other (a note pricing near
    # its coupon). Anchor BOTH labels to the LEFT of their line so the text
    # grows inward (never off the right edge), and stagger them vertically —
    # Mean at the top, Coupon a row lower via yshift — so they never overlap.
    fig.add_vline(
        x=expected_irr, line_dash="dash", line_color=_GREEN_MID, line_width=1.5,
        annotation_text=tr("chart_mean", v=f"{expected_irr:.2%}"),
        annotation_position="top left",
        annotation_font_size=11,
        annotation_yshift=2,
    )
    fig.add_vline(
        x=coupon_rate_pa, line_dash="dot", line_color=_GREY, line_width=1.5,
        annotation_text=tr("chart_coupon_pa", v=f"{coupon_rate_pa:.2%}"),
        annotation_position="top left",
        annotation_font_size=11,
        annotation_yshift=-18,
    )
    fig.add_vline(
        x=0, line_dash="solid", line_color=_RED, line_width=1,
        annotation_text="0%",
        annotation_position="bottom right",
        annotation_font_size=10,
    )

    fig.update_layout(
        title=tr("chart_irr_title") + _clip_note,
        xaxis=dict(title=tr("chart_irr_xaxis"), tickformat=".1%", range=x_range),
        yaxis=dict(title=tr("chart_irr_yaxis"), tickformat=".1%"),
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
        fill="toself", fillcolor=_FILL_OUTER,
        line=dict(color="rgba(0,0,0,0)"),
        name=tr("pct_5_95"),
    ))
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[3], bands[1][::-1]]),
        fill="toself", fillcolor=_FILL_INNER,
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
        fill="toself", fillcolor=_FILL_OUTER,
        line=dict(color="rgba(0,0,0,0)"), name=tr("pct_5_95"),
    ))
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[3], bands[1][::-1]]),
        fill="toself", fillcolor=_FILL_INNER,
        line=dict(color="rgba(0,0,0,0)"), name=tr("pct_25_75"),
    ))
    fig.add_trace(go.Scatter(
        x=t_grid, y=bands[2],
        mode="lines", name=tr("median"),
        line=dict(color=_GREEN_MID, width=2),
    ))
    fig.add_hline(
        y=knock_in_barrier, line_dash="dash", line_color=_RED,
        annotation_text=tr("chart_ki_barrier", lvl=f"{knock_in_barrier:.0%}"),
        annotation_position="bottom right",
    )
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule, tr, x0=0.0)
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
        name=tr("chart_worst_of"),
        line=dict(color=_GREEN_DARK, width=2.5),
    ))
    fig.add_hline(
        y=knock_in_barrier, line_dash="dash", line_color=_RED,
        annotation_text=tr("chart_ki_barrier", lvl=f"{knock_in_barrier:.0%}"),
        annotation_position="bottom right",
    )
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule, tr, x0=0)
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
        color_continuous_scale=[[0, _RED], [0.5, _WHITE], [1, _NAVY]],
        zmin=zmin, zmax=zmax,
        title=title, aspect="auto",
    )
    fig.update_layout(coloraxis_showscale=False)
    return _apply_theme(fig)


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
        labels={"Outcome": tr("chart_outcome_axis")},
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
        title = tr("chart_worst_asset_at_call")

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
    return _apply_theme(fig)


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
        labels={
            "Issue Date":      tr("chart_issue_date_axis"),
            "IRR":             tr("chart_irr_axis"),
            "Outcome":         tr("chart_outcome_axis"),
            "Payout":          tr("chart_payout_axis"),
            "Worst Asset":     tr("chart_worst_asset_axis"),
            "Worst Final Perf":tr("chart_worst_final_perf_axis"),
        },
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
        title=tr("chart_hist_prices_title"),
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
        mode="lines", name=tr("chart_worst_of"),
        line=dict(color=_GREEN_DARK, width=2.5),
    ))

    # Barriers — KI, coupon (when distinct), and autocall (flat or stepped)
    fig.add_hline(y=knock_in_barrier, line_dash="dash", line_color=_RED,
                  annotation_text=tr("chart_ki_barrier", lvl=f"{knock_in_barrier:.1%}"),
                  annotation_position="bottom right")
    _add_coupon_barrier(fig, coupon_barrier, knock_in_barrier, tr)
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule, tr,
                          x0=hist_prices.index[issue_idx])

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
        label   = tr("chart_period_called", p=q + 1) if is_call else f"P{q+1}"

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

    outcome = (tr("chart_outcome_autocalled_p", q=call_quarter)
               if call_quarter > 0 else tr("outcome_maturity"))
    fig.update_layout(
        title=tr("chart_hist_wof_title", issue=issue_date.date(), outcome=outcome),
        xaxis=dict(title=tr("date_axis")),
        yaxis=dict(title=tr("chart_perf_vs_issue"), tickformat=".0%"),
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
        mode="lines", name=tr("chart_worst_of"),
        line=dict(color=_GREEN_DARK, width=2.5),
    ))

    # Barriers — KI, coupon (when distinct), and autocall (flat or stepped)
    fig.add_hline(y=knock_in_barrier, line_dash="dash", line_color=_RED,
                  annotation_text=tr("chart_ki_barrier", lvl=f"{knock_in_barrier:.1%}"),
                  annotation_position="bottom right")
    _add_coupon_barrier(fig, coupon_barrier, knock_in_barrier, tr)
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule, tr, x0=issue_date)

    # Today line
    if today in dates or today >= dates[0]:
        fig.add_vline(x=today.isoformat(), line_dash="solid", line_color="#2c3e50",
                      line_width=2,
                      annotation_text=tr("chart_today"), annotation_position="top left")

    # Past observation markers (status precomputed by replay_note)
    for m in obs_markers:
        if m["autocalled"]:
            tip = tr("chart_marker_autocalled", label=m["label"]) + (
                tr("chart_marker_premium", v=f"{m['amount']:.4%}") if m["amount"] > 0 else "")
            color, symbol, size = _GREEN_MID, "star", 12
        elif m["paid"]:
            tip = tr("chart_marker_coupon", label=m["label"], v=f"{m['amount']:.4%}")
            color, symbol, size = _GREEN_MID, "circle", 9
        else:
            tip = tr("chart_marker_coupon_missed", label=m["label"])
            color, symbol, size = _RED, "circle", 9
        fig.add_trace(go.Scatter(
            x=[m["date"]], y=[m["wof"]],
            mode="markers",
            marker=dict(size=size, color=color, symbol=symbol,
                        line=dict(width=1.5, color="white")),
            name=tip, showlegend=True,
            hovertemplate=f"{tip}<br>{tr('chart_worst_of')}: {m['wof']:.1%}<extra></extra>",
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
        title=tr("chart_live_title", issue=issue_date.date(), mat=maturity_date.date()),
        xaxis=dict(title=tr("date_axis")),
        yaxis=dict(title=tr("chart_perf_vs_issue"), tickformat=".0%"),
        hovermode="x unified",
        legend=dict(x=1.01, y=1, xanchor="left"),
    )
    return _plain_layout(fig)