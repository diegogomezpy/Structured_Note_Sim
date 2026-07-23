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

from contextvars import ContextVar

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from translations import Translator

# ---------------------------------------------------------------------------
# Institutional palette — navy / blue, matching the PDF report and web theme.
# These exact hex values are the source palette the PDF report's branded
# recolouring (app/pdf_report.py) keys on, so do not change the values without
# updating the _SRC_* constants there.
# ---------------------------------------------------------------------------
_NAVY         = "#1a2e4a"   # primary / worst-of line / dark series
_BLUE         = "#2563eb"   # accent / median / primary series
_BLUE_LIGHT   = "#60a5fa"   # light blue secondary series
_RED          = "#dc2626"   # barrier / loss / negative
_GREY         = "#6b7280"   # warm grey — secondary lines/text
_GREEN        = "#16a34a"   # coupon paid / positive event
_WHITE        = "white"
# Brand-neutral green/teal categorical ramp for discrete multi-slice charts
# (e.g. the worst-asset donut) so they read on-brand instead of a clashing blue.
_CATEGORICAL  = ["#007953", "#2e7e8c", "#9aa80f", "#2bc275", "#0b3d2e", "#1c5566"]

# Extra categorical colours for multi-asset charts (>3 underlyings)
_SERIES_COLORS = [_BLUE, _NAVY, _BLUE_LIGHT, "#0891b2", "#7c3aed", "#0d9488"]

_BASE_FONT = "IBM Plex Sans, Arial, sans-serif"

# Light fill tints for fan-chart bands (blue, low alpha)
_FILL_OUTERMOST = "rgba(37,99,235,0.04)"   # 1st–99th pct (faintest, widest)
_FILL_OUTER = "rgba(37,99,235,0.08)"
_FILL_INNER = "rgba(37,99,235,0.20)"
# Green (participation payoff palette) equivalents of the fan percentile fills.
_FILL_OUTERMOST_G = "rgba(22,163,74,0.05)"
_FILL_OUTER_G = "rgba(22,163,74,0.09)"
_FILL_INNER_G = "rgba(22,163,74,0.20)"


# ── brand-tunable chart options ───────────────────────────────────────────────
# Every builder ends with _apply_theme(fig), so this dict is the single place a
# brand can restyle all 19 figures. `set_chart_options()` is called from the PDF
# adapter with the branding config before the figures are built; defaults below
# reproduce the original look exactly, so an un-themed report is unchanged.
CHART_OPTION_DEFAULTS: dict = {
    "bg_color":      _WHITE,      # plot + paper background
    "grid_color":    "#f1f5f9",   # gridlines
    "axis_color":    "#e5e7eb",   # axis + zero lines
    "label_color":   _GREY,       # tick + axis-title text
    "text_color":    _NAVY,       # base / title / legend text
    "font_size":     12.0,        # base size; ticks -1, title +3
    "series_colors": None,        # list[str] — the multi-series colourway
    "band_opacity":  1.0,         # multiplier on percentile-band alphas
    "line_width":    1.0,         # multiplier on series line widths
}
# Held in a ContextVar, not a module dict. FastAPI runs sync endpoints in a
# threadpool, so two branded reports building at once would otherwise trade
# palettes mid-render and each emit some of the other brand's figures. A lock
# would serialise them instead, which is worse: a fast preview would queue
# behind a slow full report. A ContextVar gives each caller its own view with no
# contention at all.
_CHART_OPTS_VAR: ContextVar[dict] = ContextVar("chart_opts", default=CHART_OPTION_DEFAULTS)


def _opts() -> dict:
    return _CHART_OPTS_VAR.get()


def set_chart_options(opts: dict | None):
    """Install brand chart options (see CHART_OPTION_DEFAULTS). Unknown/None
    values fall back to the default, so a partial dict is fine.

    Returns the token to hand back to `reset_chart_options`, so nested or
    concurrent renders unwind to whatever was in force before rather than
    stamping everyone back to the stock look.
    """
    merged = dict(CHART_OPTION_DEFAULTS)
    for k, v in (opts or {}).items():
        if k in merged and v not in (None, ""):
            merged[k] = v
    return _CHART_OPTS_VAR.set(merged)


def reset_chart_options(token=None) -> None:
    """Restore what was in force before the matching `set_chart_options`."""
    if token is not None:
        _CHART_OPTS_VAR.reset(token)
    else:
        _CHART_OPTS_VAR.set(dict(CHART_OPTION_DEFAULTS))


def _scale_rgba_alpha(color: str, factor: float) -> str:
    """Scale the alpha of an 'rgba(r,g,b,a)' string, leaving anything else be."""
    if not isinstance(color, str) or not color.startswith("rgba("):
        return color
    try:
        parts = color[5:-1].split(",")
        r, g, b = (p.strip() for p in parts[:3])
        a = float(parts[3])
        return f"rgba({r},{g},{b},{max(0.0, min(1.0, a * factor)):.4f})"
    except Exception:
        return color


def _apply_trace_options(fig: go.Figure) -> None:
    """Apply the trace-level options that can't be expressed in the layout:
    percentile-band alpha and series line width. Done centrally here so every
    builder inherits it without touching 19 functions."""
    band = float(_opts().get("band_opacity") or 1.0)
    lw = float(_opts().get("line_width") or 1.0)
    if band == 1.0 and lw == 1.0:
        return
    for tr in fig.data:
        if band != 1.0:
            fc = getattr(tr, "fillcolor", None)
            if fc:
                try:
                    tr.fillcolor = _scale_rgba_alpha(fc, band)
                except Exception:
                    pass
        if lw != 1.0:
            line = getattr(tr, "line", None)
            w = getattr(line, "width", None) if line is not None else None
            if w:
                try:
                    tr.line.width = max(0.2, float(w) * lw)
                except Exception:
                    pass


def _apply_theme(fig: go.Figure) -> go.Figure:
    """
    Shared clean theme for every figure: background, IBM Plex Sans font, text
    and gridline colours, no Plotly logo. Preserves all existing traces, barrier
    lines, markers and titles. Reads the active chart options so a brand can restyle every
    chart from its config (defaults reproduce the original look exactly).
    """
    o = _opts()
    bg, grid, axis = o["bg_color"], o["grid_color"], o["axis_color"]
    label, text = o["label_color"], o["text_color"]
    fs = float(o["font_size"] or 12.0)
    colorway = o.get("series_colors") or _SERIES_COLORS
    fig.update_layout(
        plot_bgcolor=bg,
        paper_bgcolor=bg,
        font=dict(family=_BASE_FONT, size=fs, color=text),
        title=dict(font=dict(family=_BASE_FONT, size=fs + 3, color=text)),
        legend=dict(
            font=dict(family=_BASE_FONT, size=fs - 1, color=text),
            bgcolor="rgba(255,255,255,0.6)",
            bordercolor=axis, borderwidth=0,
        ),
        margin=dict(l=60, r=30, t=50, b=50),
        modebar_remove=["logo", "sendDataToCloud", "lasso2d", "select2d"],
        colorway=list(colorway),
    )
    fig.update_xaxes(
        linecolor=axis, gridcolor=grid, zerolinecolor=axis,
        title_font=dict(family=_BASE_FONT, size=fs, color=label),
        tickfont=dict(family=_BASE_FONT, size=fs - 1, color=label),
    )
    fig.update_yaxes(
        linecolor=axis, gridcolor=grid, zerolinecolor=axis,
        title_font=dict(family=_BASE_FONT, size=fs, color=label),
        tickfont=dict(family=_BASE_FONT, size=fs - 1, color=label),
    )
    _apply_trace_options(fig)
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
        # On a date axis the x values are pd.Timestamps; kaleido (PDF export)
        # can't JSON-serialise a raw Timestamp, so pass ISO strings — identical on
        # the date axis, and the browser path is unaffected. (Numeric axes pass through.)
        xs = [x.isoformat() if isinstance(x, pd.Timestamp) else x for x in xs]
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

def _build_irr_discrete(
    irr_all:         np.ndarray,
    total_all:       np.ndarray | None,
    autocall_events: np.ndarray,
    tr:              Translator,
) -> go.Figure:
    """Discrete outcome breakdown — the clean fallback for a near-degenerate IRR
    distribution (see ``build_irr_distribution``). When a note autocalls with
    very high probability almost every path lands on one IRR, so a continuous
    histogram collapses to a single spike in an empty grid that reads as a
    rendering glitch. Instead show one bar per economic outcome (autocalled /
    held to maturity / capital loss).

    Two panels: (1) the PROBABILITY of each outcome, and (2) the mean TOTAL
    RETURN and mean IRR p.a. within each outcome — so the reader sees both how
    likely each scenario is and how much it pays. The second panel is omitted
    when per-path total returns aren't supplied."""
    n = len(irr_all)
    loss_mask   = irr_all < 0
    called_mask = (autocall_events > 0) & ~loss_mask
    mat_mask    = ~called_mask & ~loss_mask

    specs = [
        (tr("chart_irr_bucket_autocall"), called_mask, _BLUE_LIGHT),
        (tr("chart_irr_bucket_maturity"), mat_mask,    _NAVY),
        (tr("chart_irr_bucket_loss"),     loss_mask,   _RED),
    ]
    labels, shares, colors, masks = [], [], [], []
    for lbl, mask, col in specs:
        cnt = int(np.count_nonzero(mask))
        if cnt == 0:                       # drop empty outcomes — no zero bars
            continue
        labels.append(lbl)
        shares.append(cnt / n)
        colors.append(col)
        masks.append(mask)

    have_returns = total_all is not None and len(total_all) == n
    n_cols = 2 if have_returns else 1
    titles = [tr("chart_disc_prob_panel")]
    if have_returns:
        titles.append(tr("chart_disc_return_panel"))
    fig = make_subplots(rows=1, cols=n_cols, subplot_titles=titles,
                        horizontal_spacing=0.16)

    # ── Panel 1 — probability of each outcome ──────────────────────────────
    # Force the dominant (near-100%) bar's label INSIDE: with "auto" the static
    # PDF renderer (kaleido) places it outside and it gets clipped at the top.
    pos = ["inside" if s >= 0.55 else "outside" for s in shares]
    fig.add_trace(go.Bar(
        x=labels, y=shares, text=[f"{s:.1%}" for s in shares],
        textposition=pos, insidetextanchor="end",
        marker_color=colors, width=0.55, cliponaxis=False,
        textfont=dict(size=13), showlegend=False,
    ), row=1, col=1)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.0], row=1, col=1)
    fig.update_xaxes(type="category", row=1, col=1)

    # ── Panel 2 — mean total return & mean IRR p.a. within each outcome ─────
    if have_returns:
        mean_tr  = [float(np.mean(total_all[m])) for m in masks]
        mean_irr = [float(np.mean(irr_all[m]))   for m in masks]
        fig.add_trace(go.Bar(
            x=labels, y=mean_tr, name=tr("chart_disc_total_return"),
            text=[f"{v:+.1%}" for v in mean_tr], textposition="outside",
            marker_color=_NAVY, cliponaxis=False, textfont=dict(size=11),
        ), row=1, col=2)
        fig.add_trace(go.Bar(
            x=labels, y=mean_irr, name=tr("chart_disc_irr_pa"),
            text=[f"{v:+.1%}" for v in mean_irr], textposition="outside",
            marker_color=_BLUE, cliponaxis=False, textfont=dict(size=11),
        ), row=1, col=2)
        _vals = mean_tr + mean_irr
        lo, hi = min(0.0, min(_vals)), max(0.0, max(_vals))
        span = (hi - lo) or 0.1
        fig.add_hline(y=0, line_color=_GREY, line_width=1, row=1, col=2)
        fig.update_yaxes(tickformat=".0%",
                         range=[lo - span * 0.28, hi + span * 0.28], row=1, col=2)
        fig.update_xaxes(type="category", row=1, col=2)

    # No chart title: the app renders an "IRR distribution" subheader above this
    # figure and the PDF strips chart titles, so a title here only duplicates it.
    fig.update_layout(showlegend=have_returns, barmode="group",
                      bargap=0.45, bargroupgap=0.1)
    for ann in fig.layout.annotations:          # subplot titles
        ann.font.size = 12
    fig = _apply_theme(fig)
    # Override post-theme: a horizontal legend centred below the panels (for the
    # two return series), with extra bottom room so it clears the x-tick labels.
    if have_returns:
        fig.update_layout(
            margin=dict(l=45, r=25, t=46, b=72),
            legend=dict(orientation="h", x=0.5, xanchor="center",
                        y=-0.22, yanchor="top"),
        )
    return fig


def build_irr_distribution(
    annualized_returns: np.ndarray,
    total_returns:      np.ndarray | None,
    autocall_events:    np.ndarray,
    expected_irr:       float,
    coupon_rate_pa:     float,      # p.a. coupon for reference line
    tr:                 Translator,
) -> go.Figure:
    """
    IRR distribution shown as a discrete OUTCOME breakdown — the default view for
    every note. One bar per economic outcome (autocalled / held to maturity /
    capital loss): panel 1 is the probability of each, panel 2 the mean total
    return and mean IRR p.a. within each (see ``_build_irr_discrete``).

    This replaced the continuous IRR histogram as the default. Structured notes
    concentrate their mass on a handful of outcomes (a high-autocall note puts
    nearly every path on one IRR), so a histogram collapses to a single spike that
    reads as a render glitch; the outcome view is clear for those AND stays
    meaningful for dispersed notes. ``expected_irr`` / ``coupon_rate_pa`` are kept
    in the signature for call-site compatibility but no longer drawn.
    """
    return _build_irr_discrete(annualized_returns, total_returns,
                               autocall_events, tr)


# ---------------------------------------------------------------------------
# Tab 2 — per-asset fan chart
# ---------------------------------------------------------------------------

def build_fan_chart(
    paths:      np.ndarray | None,   # (n_paths, N+1) single asset, or None if bands given
    asset_name: str,
    t_grid:     np.ndarray,
    obs_labels: list[tuple[str, float]],  # [(label, t), ...] e.g. [("3M", 0.25)]
    tr:         Translator,
    bands:      np.ndarray | None = None,  # precomputed (7, N+1) percentile bands
) -> go.Figure:
    # Tenors are quoted in MONTHS throughout the app, so the time axis is too.
    # The engine works in years; convert here, at the render boundary only.
    t_grid = np.asarray(t_grid, dtype=float) * 12.0
    obs_labels = [(lbl, tv * 12.0) for lbl, tv in obs_labels]
    # `bands` is the [1,5,25,50,75,95,99]-percentile envelope, precomputed once at
    # run-time so this doesn't rescan the full path array on every rerun (and the
    # array need not be kept in RAM just for the fan). Falls back to computing it.
    pcts = [1, 5, 25, 50, 75, 95, 99]
    if bands is None:
        bands = np.percentile(paths, pcts, axis=0)
    S0 = float(bands[3, 0])        # every path starts at S0, so any pct at t=0 == S0
    # index map: 0=1st 1=5th 2=25th 3=median 4=75th 5=95th 6=99th
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[6], bands[0][::-1]]),
        fill="toself", fillcolor=_FILL_OUTERMOST,
        line=dict(color="rgba(0,0,0,0)"),
        name=tr("pct_1_99"),
    ))
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[5], bands[1][::-1]]),
        fill="toself", fillcolor=_FILL_OUTER,
        line=dict(color="rgba(0,0,0,0)"),
        name=tr("pct_5_95"),
    ))
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[4], bands[2][::-1]]),
        fill="toself", fillcolor=_FILL_INNER,
        line=dict(color="rgba(0,0,0,0)"),
        name=tr("pct_25_75"),
    ))
    fig.add_trace(go.Scatter(
        x=t_grid, y=bands[3],
        mode="lines", name=tr("median"),
        line=dict(color=_BLUE, width=2),
    ))
    fig.add_hline(y=S0, line_dash="dash", line_color=_GREY,
                  annotation_text="S₀", annotation_position="right")

    for label, t_val in obs_labels:
        fig.add_vline(x=t_val, line_dash="dot", line_color="#aaa",
                      annotation_text=label, annotation_position="top")

    fig.update_layout(
        title=f"{asset_name} — {tr('simulated_price_dist')}",
        xaxis=dict(title=tr("time_months"), tickformat=".0f"),
        yaxis=dict(title=tr("price")),
        hovermode="x unified",
    )
    _apply_theme(fig)
    # Legend below the plot (horizontal) so the percentile bands / median key
    # never sit on top of the chart itself.
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
        margin=dict(l=60, r=30, t=50, b=78),
    )
    return fig


# ---------------------------------------------------------------------------
# Tab 2 — worst-of fan chart
# ---------------------------------------------------------------------------

def build_wof_fan(
    worst_of_paths:   np.ndarray | None,   # or None when `bands` is supplied
    t_grid:           np.ndarray,
    knock_in_barrier: float,
    obs_labels:       list[tuple[str, float]],
    tr:               Translator,
    autocall_barrier: float | None = None,
    autocall_schedule: list[tuple[float, float]] | None = None,
    bands:            np.ndarray | None = None,  # precomputed (7, N+1) percentile bands
    participation:    bool = False,   # Participation note: no autocall/knock-in barriers
) -> go.Figure:
    # Tenors are quoted in MONTHS throughout the app, so the time axis is too.
    # The engine works in years; convert here, at the render boundary only.
    t_grid = np.asarray(t_grid, dtype=float) * 12.0
    obs_labels = [(lbl, tv * 12.0) for lbl, tv in obs_labels]
    if autocall_schedule:
        autocall_schedule = [(tv * 12.0, lv) for tv, lv in autocall_schedule]
    # Precomputed once at run-time (see build_fan_chart) so this doesn't rescan the
    # full worst-of array on every rerun. Falls back to computing it.
    pcts = [1, 5, 25, 50, 75, 95, 99]
    if bands is None:
        bands = np.percentile(worst_of_paths, pcts, axis=0)
    # index map: 0=1st 1=5th 2=25th 3=median 4=75th 5=95th 6=99th
    # Participation notes render in the green payoff palette (matching the redemption
    # distribution / payoff-profile charts) rather than the phoenix blue.
    _f_out, _f_mid, _f_in = ((_FILL_OUTERMOST_G, _FILL_OUTER_G, _FILL_INNER_G)
                             if participation else (_FILL_OUTERMOST, _FILL_OUTER, _FILL_INNER))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[6], bands[0][::-1]]),
        fill="toself", fillcolor=_f_out,
        line=dict(color="rgba(0,0,0,0)"), name=tr("pct_1_99"),
    ))
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[5], bands[1][::-1]]),
        fill="toself", fillcolor=_f_mid,
        line=dict(color="rgba(0,0,0,0)"), name=tr("pct_5_95"),
    ))
    fig.add_trace(go.Scatter(
        x=np.concatenate([t_grid, t_grid[::-1]]),
        y=np.concatenate([bands[4], bands[2][::-1]]),
        fill="toself", fillcolor=_f_in,
        line=dict(color="rgba(0,0,0,0)"), name=tr("pct_25_75"),
    ))
    fig.add_trace(go.Scatter(
        x=t_grid, y=bands[3],
        mode="lines", name=tr("median"),
        line=dict(color=_GREEN if participation else _BLUE, width=2),
    ))
    # A Participation note has no knock-in / autocall barriers — drawing them (at the
    # placeholder 0% / 200% those fields hold) would be meaningless, so skip them.
    if not participation:
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
        xaxis=dict(title=tr("time_months"), tickformat=".0f"),
        yaxis=dict(title=tr("perf_vs_initial"), tickformat=".0%"),
        hovermode="x unified",
    )
    _apply_theme(fig)
    # Legend below the plot (horizontal) so the percentile bands / median key
    # never sit on top of the chart itself.
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
        margin=dict(l=60, r=30, t=50, b=78),
    )
    return fig


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
    marker_info:      list[dict] | None = None,
    title:            str | None = None,
) -> go.Figure:
    """Worst-of performance path with per-observation event markers.

    The note's life ends at the autocall: when ``autocall_q > 0`` the worst-of
    line and the observation markers stop at the call step — nothing is drawn for
    the periods that never happened.

    ``marker_info`` is one dict per live observation, built by the caller from the
    canonical engine (replay_note) so the legend spells out the full note state at
    each date: worst-of level, the coupon outcome (paid amount, memory multiplier
    or pending count, or an accruing/paid premium for growth autocalls), the
    autocall, and at maturity the knock-in / par-redemption result. Each carries:
        {"text": str, "kind": one of call_coupon|call|coupon|missed|knock_in}
    ``kind`` drives the marker colour/shape; ``text`` is the legend label. Pass
    ``asset_paths`` to overlay the underlyings (dashed). ``title`` overrides the
    header."""
    asset_colors = [_BLUE, _BLUE_LIGHT, _NAVY, "#f39c12", "#9b59b6"]
    fig = go.Figure()

    n_obs   = len(obs_steps)
    # Truncate the displayed life at the autocall — the note no longer exists.
    cut     = obs_steps[autocall_q - 1] if autocall_q > 0 else len(worst_path) - 1
    x_full  = np.arange(cut + 1)

    # Per-asset lines behind worst-of (only when explicitly requested)
    if asset_paths is not None and asset_names is not None:
        for i, name in enumerate(asset_names):
            fig.add_trace(go.Scatter(
                x=x_full, y=asset_paths[:cut + 1, i], mode="lines", name=name,
                line=dict(color=asset_colors[i % len(asset_colors)], width=1.2, dash="dot"),
                opacity=0.65,
            ))

    fig.add_trace(go.Scatter(
        x=x_full, y=worst_path[:cut + 1], mode="lines",
        name=tr("chart_worst_of"),
        line=dict(color=_NAVY, width=2.5),
    ))
    fig.add_hline(
        y=knock_in_barrier, line_dash="dash", line_color=_RED,
        annotation_text=tr("chart_ki_barrier", lvl=f"{knock_in_barrier:.0%}"),
        annotation_position="bottom right",
    )
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule, tr, x0=0)
    # kind → (colour, symbol, size). Star = autocall (green if it also paid),
    # red ✕ = capital loss at maturity, green/grey circle = coupon paid / missed.
    _kind_style = {
        "call_coupon": (_GREEN, "star",   14),
        "call":        (_BLUE,  "star",   14),
        "coupon":      (_GREEN, "circle", 11),
        "missed":      (_GREY,  "circle", 11),
        "knock_in":    (_RED,   "x",      13),
    }
    for i, info in enumerate(marker_info or []):
        if i >= len(obs_steps):
            break
        step, label = obs_steps[i], obs_labels[i]
        color, marker_sym, sz = _kind_style.get(info.get("kind"), (_GREY, "circle", 11))
        fig.add_trace(go.Scatter(
            x=[step], y=[worst_path[step]], mode="markers",
            marker=dict(size=sz, color=color, symbol=marker_sym,
                        line=dict(width=1.5, color=_WHITE)),
            name=info.get("text", label),
        ))
        fig.add_vline(x=step, line_dash="dot", line_color="#aaa",
                      annotation_text=label, annotation_position="top")

    fig.update_layout(
        title=title or tr("wof_path_title", n=path_num),
        yaxis=dict(title=tr("perf_vs_initial"), tickformat=".0%"),
        xaxis=dict(title=tr("time_step")),
        hovermode="x unified",
    )
    return _apply_theme(fig)


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
    fig = _apply_theme(fig)
    # Long asset names get clipped on the y-axis (and x-axis) under the fixed
    # theme margins — let plotly grow the margins to fit the full tick labels.
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    return fig


# ---------------------------------------------------------------------------
# Backtest — outcome bar chart
# ---------------------------------------------------------------------------

def build_sample_paths(
    wof_paths,
    t_grid,
    autocall_period,
    knock_in_mask,
    knock_in_barrier: float,
    autocall_barrier: float,
    obs_pairs,
    tr: Translator,
    n_show: int = 300,
) -> go.Figure:
    """Spaghetti of a sample of worst-of trajectories, coloured by outcome
    (autocalled blue / held-to-maturity green / knocked-in red) — the report
    version of the web sample-paths chart. Three concatenated traces (one per
    outcome) so the figure stays light even with hundreds of paths."""
    # Tenors are quoted in MONTHS throughout the app, so the time axis is too.
    # The engine works in years; convert here, at the render boundary only.
    t_grid = np.asarray(t_grid, dtype=float) * 12.0
    obs_pairs = [(lbl, tv * 12.0) for lbl, tv in obs_pairs]
    wof = np.asarray(wof_paths)
    P = wof.shape[0]
    ap = np.asarray(autocall_period)
    ki = np.asarray(knock_in_mask)
    idx = np.arange(P)
    if P > n_show:
        idx = np.random.default_rng(0).choice(P, size=n_show, replace=False)
    kind = np.where(ki[idx], "ki", np.where(ap[idx] > 0, "ac", "mat"))
    # Draw order matters: the dominant autocalled mass goes at the BACK (so it
    # doesn't blend everything into an indistinct teal), with held-to-maturity and
    # the rarer knocked-in paths on top, each in a clearly saturated colour and a
    # slightly heavier weight so individual trajectories stay distinguishable.
    spec = [
        ("ac",  "rgba(37,99,235,0.40)",  0.7, tr("sp_autocalled")),
        ("mat", "rgba(22,163,74,0.65)",  0.8, tr("sp_held")),
        ("ki",  "rgba(220,38,38,0.80)",  1.0, tr("knocked_in")),
    ]
    tg = list(np.asarray(t_grid))
    fig = go.Figure()
    for code, col, w, name in spec:
        sel = idx[kind == code]
        if len(sel) == 0:
            continue
        xs, ys = [], []
        for i in sel:
            xs.extend(tg); xs.append(None)
            ys.extend(list(wof[i])); ys.append(None)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=name,
                                 line=dict(color=col, width=w), hoverinfo="skip"))
    fig.add_hline(y=autocall_barrier, line_dash="dash", line_color=_BLUE,
                  annotation_text=tr("chart_autocall_barrier_lvl", lvl=f"{autocall_barrier:.0%}"),
                  annotation_position="right")
    fig.add_hline(y=knock_in_barrier, line_dash="dash", line_color="#dc2626",
                  annotation_text=tr("chart_ki_barrier", lvl=f"{knock_in_barrier:.0%}"),
                  annotation_position="right")
    for label, t_val in (obs_pairs or []):
        fig.add_vline(x=t_val, line_dash="dot", line_color="#bbb")
    fig.update_layout(
        title=tr("sample_paths_fig"),
        xaxis=dict(title=tr("time_months"), tickformat=".0f"),
        yaxis=dict(title=tr("perf_vs_initial"), tickformat=".0%"),
    )
    _apply_theme(fig)
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=60, r=40, t=50, b=72),
    )
    return fig


def build_outcome_breakdown(
    autocall_by_period,
    prob_maturity: float,
    prob_knock_in_total: float,
    tr: Translator,
) -> go.Figure:
    """How 100% of paths resolve, as one horizontal stacked bar: autocalled at
    each period (blue ramp) → redeemed at par (green) → knocked in (red).
    Mirrors the web Outcome-breakdown waterfall so the report carries the graph."""
    abp = [float(x) for x in (autocall_by_period or [])]
    n = len(abp)
    redeemed = max(0.0, float(prob_maturity or 0.0) - float(prob_knock_in_total or 0.0))
    ki = float(prob_knock_in_total or 0.0)
    blues = ["#1e3a8a", "#1d4ed8", "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd"]

    fig = go.Figure()

    def _seg(name, frac, color, *, group=None, show=True, legend_name=None) -> bool:
        """Add one stacked segment. `legend_name` (when given) is what shows in the
        legend, while `name` still drives the per-segment hover — so the autocall
        ramp can share ONE legend entry yet keep its per-period hover labels."""
        if frac <= 0.002:
            return False
        fig.add_trace(go.Bar(
            y=["_"], x=[frac], orientation="h", name=legend_name or name, marker_color=color,
            marker_line_width=0, legendgroup=group, showlegend=show,
            text=[f"{frac:.0%}"] if frac > 0.06 else [""],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(color="#ffffff", size=12),
            hovertemplate=f"{name}: %{{x:.1%}}<extra></extra>",
        ))
        return True

    # Autocall periods share a single legend entry ("Autocalled early") so the
    # legend can't overflow/overlap when there are many observation periods — the
    # colour ramp + inline % + per-period hover still distinguish each period.
    shown_ac = False
    for i, f in enumerate(abp):
        added = _seg(tr("autocalled_p").format(p=i + 1), f, blues[min(i, len(blues) - 1)],
                     group="ac", show=not shown_ac, legend_name=tr("autocalled_early"))
        if added and not shown_ac:
            shown_ac = True
    _seg(tr("redeemed_at_par"), redeemed, "#16a34a")
    _seg(tr("knocked_in"), ki, "#dc2626")

    fig.update_layout(
        title=tr("outcome_breakdown"),
        barmode="stack", bargap=0.4,
        xaxis=dict(title=tr("outcome_axis"), tickformat=".0%", range=[0, 1]),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
    )
    _apply_theme(fig)
    fig.update_layout(margin=dict(l=24, r=24, t=50, b=64))
    return fig


def build_redemption_distribution(nominal_payoffs, terms, tr: Translator) -> go.Figure:
    """Histogram of maturity redemption (% of notional) for a Participation Note,
    with reference lines at par and (if set) the cap. Replaces the autocall outcome
    breakdown, which is meaningless for a note that never autocalls."""
    R = np.asarray(nominal_payoffs, dtype=float) * 100.0
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=R, nbinsx=60, marker_color="#3f8a6f", marker_line_width=0,
        hovertemplate=tr("redemption_axis") + ": %{x:.0f}%<extra></extra>",
    ))

    def _ref(x, color, label):
        fig.add_vline(x=x, line=dict(color=color, width=1.5, dash="dash"))
        fig.add_annotation(x=x, yref="paper", y=1.03, text=label, showarrow=False,
                           font=dict(size=10, color=color))
    _ref(100.0, "#6b7280", tr("lbl_par"))
    if terms.upside_cap is not None and not getattr(terms, "participation_periodic", False):
        _ref((1.0 + terms.upside_cap) * 100.0, "#9ca3af", tr("lbl_cap"))

    fig.update_layout(
        title=tr("redemption_dist"),
        xaxis=dict(title=tr("redemption_axis"), ticksuffix="%"),
        yaxis=dict(title=tr("count"), showgrid=True),
        bargap=0.02, showlegend=False,
    )
    _apply_theme(fig)
    fig.update_layout(margin=dict(l=52, r=24, t=52, b=48))
    return fig


# ---------------------------------------------------------------------------
# A/B comparison overlays (Note A vs Note B on the same underlying)
# ---------------------------------------------------------------------------
# A uses the blue-family literal (→ viridian in the web theme), B the amber-family
# literal (→ ochre) so the two series stay clearly distinct in both surfaces.
_CMP_A = "#2563eb"
_CMP_B = "#d97706"


def build_irr_compare(a_irrs, b_irrs, exp_a, exp_b, tr: Translator) -> go.Figure:
    """Overlaid IRR-p.a. distributions for two notes (A vs B), each note's
    expected IRR marked. Semi-transparent overlay so both shapes read at once."""
    A = np.asarray(a_irrs, dtype=float) * 100.0
    B = np.asarray(b_irrs, dtype=float) * 100.0
    lo = float(min(A.min(), B.min())); hi = float(max(A.max(), B.max()))
    size = max((hi - lo) / 60.0, 1e-6)
    bins = dict(start=lo, end=hi + size, size=size)
    fig = go.Figure()
    for x, name, color in ((A, tr("cmp_note_a"), _CMP_A), (B, tr("cmp_note_b"), _CMP_B)):
        fig.add_trace(go.Histogram(
            x=x, name=name, marker_color=color, opacity=0.55, marker_line_width=0,
            histnorm="percent", xbins=bins,
            hovertemplate=f"{name}: %{{x:.1f}}%<extra></extra>"))
    for x, color in ((exp_a, _CMP_A), (exp_b, _CMP_B)):
        if x is not None:
            fig.add_vline(x=float(x) * 100.0, line=dict(color=color, width=1.5, dash="dash"))
    fig.update_layout(
        title=tr("cmp_irr_dist"), barmode="overlay",
        xaxis=dict(title=tr("cmp_irr_axis"), ticksuffix="%"),
        yaxis=dict(title=tr("cmp_pct_paths"), ticksuffix="%"),
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5,
                    bgcolor="rgba(0,0,0,0)"),
    )
    _apply_theme(fig)
    fig.update_layout(margin=dict(l=52, r=24, t=52, b=64))
    return fig


def build_outcome_compare(note_a, note_b, terms_a, terms_b, tr: Translator) -> go.Figure:
    """A vs B resolution. For two Participation notes → overlaid redemption
    histograms; otherwise → two stacked outcome bars (A on top, B below), each
    autocall ramp collapsed to a single 'Autocalled (early)' segment."""
    both_part = (getattr(terms_a, "note_type", "") == "participation"
                 and getattr(terms_b, "note_type", "") == "participation")
    if both_part:
        A = np.asarray(note_a["nominal_payoffs"], dtype=float) * 100.0
        B = np.asarray(note_b["nominal_payoffs"], dtype=float) * 100.0
        lo = float(min(A.min(), B.min())); hi = float(max(A.max(), B.max()))
        size = max((hi - lo) / 60.0, 1e-6)
        bins = dict(start=lo, end=hi + size, size=size)
        fig = go.Figure()
        for x, name, color in ((A, tr("cmp_note_a"), _CMP_A), (B, tr("cmp_note_b"), _CMP_B)):
            fig.add_trace(go.Histogram(
                x=x, name=name, marker_color=color, opacity=0.55, marker_line_width=0,
                histnorm="percent", xbins=bins,
                hovertemplate=f"{name}: %{{x:.0f}}%<extra></extra>"))
        fig.add_vline(x=100.0, line=dict(color="#6b7280", width=1.5, dash="dash"))
        fig.update_layout(
            title=tr("cmp_redemption"), barmode="overlay",
            xaxis=dict(title=tr("redemption_axis"), ticksuffix="%"),
            yaxis=dict(title=tr("cmp_pct_paths"), ticksuffix="%"),
            legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5,
                        bgcolor="rgba(0,0,0,0)"))
        _apply_theme(fig)
        fig.update_layout(margin=dict(l=52, r=24, t=52, b=64))
        return fig

    fig = go.Figure()
    rows = [(tr("cmp_note_a"), note_a), (tr("cmp_note_b"), note_b)]
    first_label = rows[0][0]

    def _stack(ylabel, note):
        abp = [float(x) for x in (note.get("prob_autocall_by_period") or [])]
        ac = sum(abp)
        redeemed = max(0.0, float(note.get("prob_maturity") or 0.0)
                       - float(note.get("prob_knock_in_total") or 0.0))
        ki = float(note.get("prob_knock_in_total") or 0.0)
        for name, frac, color, grp in (
            (tr("autocalled_early"), ac, "#2563eb", "ac"),
            (tr("redeemed_at_par"), redeemed, "#16a34a", "par"),
            (tr("knocked_in"), ki, "#dc2626", "ki"),
        ):
            if frac <= 0.002:
                continue
            fig.add_trace(go.Bar(
                y=[ylabel], x=[frac], orientation="h", marker_color=color, name=name,
                legendgroup=grp, showlegend=(ylabel == first_label), marker_line_width=0,
                text=[f"{frac:.0%}"] if frac > 0.06 else [""],
                textposition="inside", insidetextanchor="middle",
                textfont=dict(color="#ffffff", size=11),
                hovertemplate=f"{ylabel} · {name}: %{{x:.1%}}<extra></extra>"))

    for ylabel, note in rows:
        _stack(ylabel, note)
    fig.update_layout(
        title=tr("cmp_outcome"), barmode="stack", bargap=0.45,
        xaxis=dict(title=tr("outcome_axis"), tickformat=".0%", range=[0, 1]),
        yaxis=dict(showgrid=False, zeroline=False, autorange="reversed"),
        legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"))
    _apply_theme(fig)
    fig.update_layout(margin=dict(l=64, r=24, t=52, b=56))
    return fig


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
    return _apply_theme(fig)


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
        hole=0.55,
        color_discrete_sequence=_CATEGORICAL,
    )
    fig.update_traces(marker=dict(line=dict(color="#ffffff", width=1.5)),
                      textposition="inside", textinfo="percent")
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

    # Degenerate guard: when every issue window produced (essentially) the same
    # IRR — a note that always autocalled at the same coupon — the points form a
    # flat line floating in a huge empty grid that looks like a render error.
    # Tighten the y-axis to a sensible band around the constant level and label
    # it, so the chart reads as the deliberate "constant N% across all windows".
    _irr = pd.to_numeric(bt["IRR"], errors="coerce").dropna()
    _flat = len(_irr) > 0 and float(_irr.max() - _irr.min()) < 0.005
    if _flat:
        c   = float(_irr.mean())
        pad = max(0.012, abs(c) * 0.6)
        y0, y1 = c - pad, c + pad
        fig.update_layout(yaxis=dict(tickformat=".1%", range=[y0, y1]))
        fig.add_annotation(
            xref="paper", x=0.5, y=c, yref="y", yshift=16,
            text=tr("chart_irr_flat_note", v=f"{c:+.1%}", n=len(_irr)),
            showarrow=False, font=dict(size=12, color=_GREY),
            bgcolor="rgba(255,255,255,0.65)",
        )
        if y0 <= 0 <= y1:               # only draw break-even if it's in view
            fig.add_hline(y=0, line_dash="dash", line_color=_GREY,
                          annotation_text=tr("break_even"),
                          annotation_position="right")
    else:
        fig.add_hline(
            y=0, line_dash="dash", line_color=_GREY,
            annotation_text=tr("break_even"),
            annotation_position="right",
        )
        fig.update_layout(yaxis=dict(tickformat=".1%"))
    return _apply_theme(fig)


# ---------------------------------------------------------------------------
# Backtest — historical normalised price paths
# ---------------------------------------------------------------------------

def build_historical_prices(
    hist_prices:  pd.DataFrame,
    bt_start:     pd.Timestamp,
    bt_end:       pd.Timestamp,
    tr:           Translator,
) -> go.Figure:
    palette = [_BLUE, _BLUE_LIGHT, _NAVY, "#f39c12", "#9b59b6"]
    fig = go.Figure()
    for i, col in enumerate(hist_prices.columns):
        normed = hist_prices[col] / hist_prices[col].iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=hist_prices.index, y=normed,
            mode="lines", name=col,
            line=dict(color=palette[i % len(palette)], width=1.5),
        ))
    # Annotations sit BELOW the line ("bottom") so they never collide with the
    # legend, which is pinned in a horizontal strip under the chart.
    fig.add_vline(x=bt_start.isoformat(), line_dash="dot", line_color=_GREY,
                  annotation_text=tr("backtest_start"), annotation_position="bottom right")
    fig.add_vline(x=bt_end.isoformat(),   line_dash="dot", line_color=_GREY,
                  annotation_text=tr("backtest_end"),   annotation_position="bottom left")
    fig.update_layout(
        title=tr("chart_hist_prices_title"),
        xaxis=dict(title=tr("date_axis")),
        yaxis=dict(title=tr("normalised_level")),
        hovermode="x unified",
        # Horizontal legend under the plot — the underlyings can spread across
        # the full width instead of bunching into the top-left corner where the
        # "Backtest start" marker label lands (the start line sits at the far
        # left, so its label and a top-left legend overlapped).
        legend=dict(orientation="h", yanchor="top", y=-0.18,
                    xanchor="center", x=0.5),
        margin=dict(t=44, b=64),
    )
    return _apply_theme(fig)


def build_underlying_price_chart(
    prices: pd.Series,
    name:   str,
    tr:     Translator,
) -> go.Figure:
    """Compact trailing-window price line for one underlying (Underlying
    Breakdown card). ``prices`` is a date-indexed close series, already sliced to
    the desired window. A single _BLUE line + faint fill (the report rebrand maps
    _BLUE → the firm accent, so it tracks the brand); no legend — one series."""
    s = prices.dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="lines", name=name, showlegend=False,
        line=dict(color=_BLUE, width=1.8),
        fill="tozeroy", fillcolor="rgba(37,99,235,0.08)",
    ))
    fig.update_layout(
        title="", showlegend=False, hovermode="x",
        xaxis=dict(title=None),
        yaxis=dict(title=tr("price_label")),
        margin=dict(l=52, r=18, t=14, b=34),
    )
    # Explicit, locale-independent month ticks. Relying on plotly/kaleido's auto
    # date axis rendered the month names in the host machine's locale (Arabic
    # glyphs appeared on some setups) and placed the year on the wrong tick.
    # Building the labels here as literal strings — not date-formatted by the
    # renderer — guarantees correct, on-language "Mon YYYY" labels everywhere.
    _MON = {"es": ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago",
                   "Sep", "Oct", "Nov", "Dic"]}.get(
        getattr(tr, "lang", "en"),
        ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
         "Oct", "Nov", "Dec"])
    if len(s):
        idx = pd.DatetimeIndex(s.index)
        months = pd.period_range(idx.min(), idx.max(), freq="M")
        step = 2 if len(months) > 7 else 1
        tickvals, ticktext = [], []
        for per in months[::step]:
            after = idx[idx >= per.to_timestamp()]
            if len(after):
                # ISO string, not a pandas Timestamp: kaleido serialises the
                # figure to JSON to render the PDF and a raw Timestamp tickval
                # raises "Type is not JSON serializable" (the chart then silently
                # dropped from the PDF, though it rendered fine in the browser).
                tickvals.append(after[0].isoformat())
                ticktext.append(f"{_MON[per.month]} {per.year}")
        fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
        # Tight y-range (don't anchor at 0 despite the fill) so detail is visible.
        lo, hi = float(s.min()), float(s.max())
        pad = (hi - lo) * 0.08 or (hi * 0.05 or 1.0)
        fig.update_yaxes(range=[lo - pad, hi + pad])
    return _apply_theme(fig)


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
    coupon_flags:     list[bool] | None = None,
    knock_in:         bool = False,
    title:            str | None = None,
) -> go.Figure:
    """
    Show per-asset performance + worst-of line for one historical issue date.

    obs_dates are the SNAPPED trading-day observation dates (the same ones the
    payoff engine evaluated). The price line AND the markers stop at the autocall
    date — the note no longer exists afterwards. The coupon barrier colours the
    markers and is drawn as its own line when it differs from the KI barrier
    (never conflate the two). At maturity the final marker spells out the
    knock-in / par outcome. For step-down notes pass
    autocall_schedule = [(date, level),...]. ``title`` overrides the header."""
    issue_idx = hist_prices.index.searchsorted(issue_date)
    # End the displayed window at the autocall date when called early, else at
    # the final observation — so the line doesn't run on past the note's life.
    _last_obs = (obs_dates[call_quarter - 1] if (call_quarter > 0 and obs_dates
                 and call_quarter <= len(obs_dates)) else (obs_dates[-1] if obs_dates else None))
    if _last_obs is not None:
        end_idx = min(int(hist_prices.index.searchsorted(_last_obs)) + 1, len(hist_prices))
    else:
        end_idx = len(hist_prices)
    slice_    = hist_prices.iloc[issue_idx:end_idx]
    dates     = slice_.index
    S0        = hist_prices.iloc[issue_idx].values.astype(float)

    # Normalise each asset to 1.0 at issue date
    perf = slice_.values / S0[np.newaxis, :]    # (days, n_assets)
    wof  = perf.min(axis=1)

    asset_colors = [_BLUE, _BLUE_LIGHT, _NAVY, "#f39c12", "#9b59b6"]
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
        line=dict(color=_NAVY, width=2.5),
    ))

    # Barriers — KI, coupon (when distinct), and autocall (flat or stepped)
    fig.add_hline(y=knock_in_barrier, line_dash="dash", line_color=_RED,
                  annotation_text=tr("chart_ki_barrier", lvl=f"{knock_in_barrier:.1%}"),
                  annotation_position="bottom right")
    _add_coupon_barrier(fig, coupon_barrier, knock_in_barrier, tr)
    _add_autocall_barrier(fig, autocall_barrier, autocall_schedule, tr,
                          x0=hist_prices.index[issue_idx])

    # Observation markers — only while the note is alive. Each entry names the
    # event (coupon, autocall, and the maturity knock-in / par outcome) so the
    # legend reads on its own.
    n_obs_bt = len(obs_dates)
    for q, obs_date in enumerate(obs_dates):
        loc = hist_prices.index.searchsorted(obs_date) - issue_idx
        if loc < 0 or loc >= len(dates):
            break
        wof_val = float(wof[loc])
        is_call          = (call_quarter == q + 1)
        reached_maturity = (call_quarter == 0 and q + 1 == n_obs_bt)
        symbol  = "star" if is_call else "circle"
        size    = 14 if is_call else 9

        # Coupon paid at this observation — prefer the engine-computed flags
        # (replay_note: honours memory, the coupon basket, coupon_at_autocall_only).
        if coupon_flags is not None:
            paid = bool(coupon_flags[q]) if q < len(coupon_flags) else False
        elif coupon_at_autocall_only:
            paid = is_call
        else:
            paid = wof_val >= coupon_barrier

        parts = [f"P{q+1}"]
        if is_call:
            parts.append(tr("leg_called"))
        elif reached_maturity:
            parts.append(tr("leg_maturity"))
        parts.append(tr("coupon_paid_label") if paid else tr("coupon_missed_label"))
        if reached_maturity:
            parts.append(tr("leg_knock_in") if knock_in else tr("leg_no_knock_in"))
        label = " · ".join(parts)

        if reached_maturity and knock_in:
            color, symbol, size = _RED, "x", 12
        elif is_call:
            color = _GREEN if paid else _BLUE
        else:
            color = _GREEN if paid else _GREY

        fig.add_trace(go.Scatter(
            # ISO string, not a raw Timestamp — kaleido (PDF) can't JSON-serialise
            # a Timestamp x and the chart would silently drop from the report.
            x=[pd.Timestamp(obs_date).isoformat()], y=[wof_val],
            mode="markers",
            marker=dict(size=size, color=color, symbol=symbol,
                        line=dict(width=1.5, color="white")),
            name=label, showlegend=True,
        ))
        fig.add_vline(x=pd.Timestamp(obs_date).isoformat(), line_dash="dot",
                      line_color="#cccccc",
                      annotation_text=f"P{q+1}", annotation_position="top")
        if is_call:
            break   # the note terminated here — later observations never happen

    outcome = (tr("chart_outcome_autocalled_p", q=call_quarter)
               if call_quarter > 0 else tr("outcome_maturity"))
    fig.update_layout(
        title=title or tr("chart_hist_wof_title", issue=issue_date.date(), outcome=outcome),
        xaxis=dict(title=tr("date_axis")),
        yaxis=dict(title=tr("chart_perf_vs_issue"), tickformat=".0%"),
        hovermode="x unified",
        legend=dict(x=1.01, y=1, xanchor="left"),
    )
    return _apply_theme(fig)

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

    # Muted, non-blue underlyings so the worst-of (brand accent) is the hero —
    # matching the Monte-Carlo path explorer.
    asset_colors = ["#64748b", "#0d9488", "#a855f7", "#d97706", "#0891b2"]
    asset_names  = list(hist_prices.columns)

    fig = go.Figure()

    # Per-asset lines (recede)
    for i, name in enumerate(asset_names):
        fig.add_trace(go.Scatter(
            x=dates, y=perf[:, i],
            mode="lines", name=name,
            line=dict(color=asset_colors[i % len(asset_colors)], width=1, dash="dot"),
            opacity=0.5,
        ))

    # Worst-of line (brand-accent hero)
    fig.add_trace(go.Scatter(
        x=dates, y=wof,
        mode="lines", name=tr("chart_worst_of"),
        line=dict(color="#2563eb", width=2.2),
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

    # Past observation markers — grouped by kind into one named legend entry each
    # (matching the path explorer), with memory payouts shown as a stack of dots.
    # ISO-string x (not a raw Timestamp): kaleido serialises to JSON for the PDF
    # and a Timestamp x raises "not JSON serializable", silently dropping the chart.
    _ev_style = {
        "call":   dict(symbol="diamond", color="#2563eb", size=11),
        "coupon": dict(symbol="circle", color="#16a34a", size=9),
        "missed": dict(symbol="circle-open", color="#d97706", size=9),
    }
    _ev_name = {"call": tr("chart_ev_call"), "coupon": tr("chart_ev_coupon"), "missed": tr("chart_ev_missed")}
    _groups: dict[str, list] = {"call": [], "coupon": [], "missed": []}
    for m in obs_markers:
        kind = "call" if m["autocalled"] else ("coupon" if m["paid"] else "missed")
        _groups[kind].append(m)
        fig.add_vline(x=pd.Timestamp(m["date"]).isoformat(), line_dash="dot", line_color="#cccccc",
                      annotation_text=m["label"], annotation_position="top")
    for kind, ms in _groups.items():
        if not ms:
            continue
        st = _ev_style[kind]
        xs, ys, texts = [], [], []
        for m in ms:
            if kind == "call":
                tip = tr("chart_marker_autocalled", label=m["label"]) + (
                    tr("chart_marker_premium", v=f"{m['amount']:.4%}") if m["amount"] > 0 else "")
            elif kind == "coupon":
                tip = tr("chart_marker_coupon", label=m["label"], v=f"{m['amount']:.4%}")
            else:
                tip = tr("chart_marker_coupon_missed", label=m["label"])
            x_iso = pd.Timestamp(m["date"]).isoformat()
            for j in range(max(1, int(m.get("released", 1)))):
                xs.append(x_iso); ys.append(m["wof"] + j * 0.03); texts.append(tip)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers", name=_ev_name[kind], showlegend=True,
            marker=dict(size=st["size"], color=st["color"], symbol=st["symbol"],
                        line=dict(width=1.5, color="white")),
            text=texts, hovertemplate="%{text}<extra></extra>",
        ))

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
    return _apply_theme(fig)


def build_participation_live_chart(
    hist_prices:    pd.DataFrame,
    issue_date:     pd.Timestamp,
    today:          pd.Timestamp,
    maturity_date:  pd.Timestamp,
    basket_kind:    str,
    tr:             "Translator",
    *,
    floor:          float | None = None,
    cap:            float | None = None,
    breakeven:      float | None = None,
    reset_markers:  list[dict] | None = None,   # cliquet: [{date,label,move,income}]
    future_resets:  list[tuple] | None = None,  # cliquet: [(label, calendar_date), ...]
) -> go.Figure:
    """Live chart for a Participation note: the participation BASKET since issue
    (the payoff reference), with the underlyings receding behind it, and the payoff
    levels — par, protection floor, cap, breakeven — as reference lines instead of
    the knock-in / autocall / coupon barriers. Cliquet notes also get a vline +
    locked-in-P&L marker at each elapsed reset date."""
    issue_idx = hist_prices.index.searchsorted(issue_date)
    S0 = hist_prices.iloc[issue_idx].values.astype(float)
    slice_ = hist_prices.iloc[issue_idx:]
    dates  = slice_.index
    perf   = slice_.values / S0[np.newaxis, :]
    if basket_kind == "best_of":
        basket = perf.max(axis=1)
    elif basket_kind == "average":
        basket = perf.mean(axis=1)
    else:
        basket = perf.min(axis=1)

    asset_colors = ["#64748b", "#0d9488", "#a855f7", "#d97706", "#0891b2"]
    asset_names  = list(hist_prices.columns)
    fig = go.Figure()
    for i, name in enumerate(asset_names):
        fig.add_trace(go.Scatter(
            x=dates, y=perf[:, i], mode="lines", name=name,
            line=dict(color=asset_colors[i % len(asset_colors)], width=1, dash="dot"),
            opacity=0.45))
    fig.add_trace(go.Scatter(
        x=dates, y=basket, mode="lines", name=tr("chart_basket"),
        line=dict(color="#2563eb", width=2.2)))

    fig.add_hline(y=1.0, line_dash="dot", line_color=_GREY,
                  annotation_text=tr("lbl_par"), annotation_position="bottom right")
    if floor is not None:
        fig.add_hline(y=floor, line_dash="dash", line_color=_RED,
                      annotation_text=tr("chart_protection", lvl=f"{floor:.0%}"),
                      annotation_position="bottom right")
    if breakeven is not None:
        fig.add_hline(y=breakeven, line_dash="dot", line_color=_RED,
                      annotation_text=tr("chart_breakeven", lvl=f"{breakeven:.0%}"),
                      annotation_position="top right")
    if cap is not None:
        fig.add_hline(y=cap, line_dash="dash", line_color=_GREY,
                      annotation_text=tr("chart_cap_lvl", lvl=f"{cap:.0%}"),
                      annotation_position="top right")

    if today >= dates[0]:
        fig.add_vline(x=today.isoformat(), line_dash="solid", line_color="#2c3e50",
                      line_width=2, annotation_text=tr("chart_today"), annotation_position="top left")

    for m in (reset_markers or []):
        x_iso = pd.Timestamp(m["date"]).isoformat()
        fig.add_vline(x=x_iso, line_dash="dot", line_color="#cccccc",
                      annotation_text=m["label"], annotation_position="top")
    if reset_markers:
        up = [m for m in reset_markers if m["income"] > 1e-9]
        dn = [m for m in reset_markers if m["income"] < -1e-9]
        fl = [m for m in reset_markers if abs(m["income"]) <= 1e-9]
        for grp, color, sym, name in (
                (up, "#16a34a", "triangle-up", tr("chart_reset_gain")),
                (dn, _RED, "triangle-down", tr("chart_reset_loss")),
                (fl, _GREY, "circle", tr("chart_reset_flat"))):
            if not grp:
                continue
            fig.add_trace(go.Scatter(
                x=[pd.Timestamp(m["date"]).isoformat() for m in grp],
                y=[float(basket[dates.searchsorted(pd.Timestamp(m["date"]))]) if pd.Timestamp(m["date"]) <= dates[-1] else 1.0 for m in grp],
                mode="markers", name=name, showlegend=True,
                marker=dict(size=11, color=color, symbol=sym, line=dict(width=1.5, color="white")),
                text=[tr("chart_reset_tip", label=m["label"], move=f"{m['move']:+.1%}", inc=f"{m['income']:+.2%}") for m in grp],
                hovertemplate="%{text}<extra></extra>"))

    for label, obs_date in (future_resets or []):
        if pd.Timestamp(obs_date) <= maturity_date:
            fig.add_vline(x=pd.Timestamp(obs_date).isoformat(), line_dash="dot",
                          line_color="#dddddd", annotation_text=label, annotation_position="top")

    fig.update_layout(
        title=tr("chart_live_title", issue=issue_date.date(), mat=maturity_date.date()),
        xaxis=dict(title=tr("date_axis")),
        yaxis=dict(title=tr("chart_basket_vs_issue"), tickformat=".0%"),
        hovermode="x unified",
        legend=dict(x=1.01, y=1, xanchor="left"))
    return _apply_theme(fig)