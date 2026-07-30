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
_INK_LINE     = "#2c3e50"   # realised history. In plotlyTheme's remap table and
                            # _rebrand_figure's, so it lands on the ink token in
                            # both surfaces — near-black on paper, near-white in
                            # dark mode. Do not swap for a colour outside those
                            # tables; an unmapped literal survives untouched.
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
    # distribution / payoff-profile charts) rather than the autocall blue.
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


def build_cliquet_profiles(
    terms,
    period_move_mean:   list[float],
    period_income_mean: list[float],
    period_move_p25:    list[float],
    period_move_p75:    list[float],
    tr:                 Translator,
    max_cols:           int = 4,
) -> "go.Figure | None":
    """A cliquet as a SERIES of payoff curves — one mini per reset period.

    Each period is an independent participation bet on that period's basket move
    (the strike resets to par, capped by `period_cap`), and the locked-in P&Ls sum
    into the final redemption. Each mini marks where that period typically lands
    (the mean simulated move, as a dot on its own curve) inside its inter-quartile
    band, so the reader sees both the shape of the bet and where it usually falls.

    The curve is evaluated by `_participation_redemption` — the SAME function that
    prices the payoff — on per-period effective terms, so this cannot drift from
    what was priced. The web mirror is web/src/components/CliquetProfiles.tsx,
    which builds the identical effective terms through participation.ts.

    Returns None when there is nothing to draw, so the caller can skip the block
    rather than emit an empty figure.
    """
    from dataclasses import replace as _replace

    from core.note import _participation_redemption

    n = min(len(period_move_mean), len(period_income_mean),
            len(period_move_p25), len(period_move_p75))
    if n < 1:
        return None

    # Per-period effective terms: the strike resets to par each period and the
    # per-period cap stands in for the note's overall upside cap. `_replace` keeps
    # every other field, so a buffer/airbag/bear downside carries through.
    eff = _replace(terms, participation_periodic=False, participation_strike=1.0,
                   upside_cap=getattr(terms, "period_cap", None))

    b = np.linspace(0.6, 1.4, 81)
    r = _participation_redemption(b, eff)

    cols = min(max_cols, n)
    rows = int(np.ceil(n / cols))
    titles = [tr("cliquet_period", k=i + 1) for i in range(n)]
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=titles,
                        horizontal_spacing=0.06,
                        vertical_spacing=0.16 if rows > 1 else 0.0,
                        shared_yaxes=True)

    for i in range(n):
        rr, cc = i // cols + 1, i % cols + 1
        lo = float(np.clip(1.0 + period_move_p25[i], b[0], b[-1]))
        hi = float(np.clip(1.0 + period_move_p75[i], b[0], b[-1]))
        fig.add_trace(go.Scatter(x=b, y=r, mode="lines", showlegend=False,
                                 line=dict(color=_GREEN, width=1.8),
                                 hovertemplate="%{x:.0%} → %{y:.1%}<extra></extra>"),
                      row=rr, col=cc)
        # IQR of the period's move, as a band behind the curve.
        #
        # Two ordering traps here, both SILENT. `add_vrect(row=, col=)` drops the
        # shape entirely if that subplot has no trace yet — no error, it just
        # doesn't appear — so the curve must be added first. And the axis cannot be
        # named by hand: subplot 1's y axis is "y", not "y1", so an f"y{i+1} domain"
        # reference raises for exactly the first mini and works for every other one.
        # `add_vrect` spans the subplot's height on its own; `layer="below"` keeps
        # it behind the curve despite being added after it.
        fig.add_vrect(x0=lo, x1=hi, fillcolor=_FILL_INNER_G, line_width=0,
                      layer="below", row=rr, col=cc)
        mb = float(np.clip(1.0 + period_move_mean[i], b[0], b[-1]))
        fig.add_trace(go.Scatter(
            x=[mb], y=[float(_participation_redemption(np.array([mb]), eff)[0])],
            mode="markers", showlegend=False,
            marker=dict(color=_INK_LINE, size=7, line=dict(color="#fff", width=1.4)),
            hovertemplate=tr("cliquet_locked", v=f"{period_income_mean[i]:+.2%}")
                          + "<extra></extra>"),
            row=rr, col=cc)
        fig.add_hline(y=1.0, line_color=_GREY, line_width=0.6, row=rr, col=cc)

    fig.update_xaxes(tickformat=".0%", tickvals=[0.6, 1.0, 1.4], tickfont=dict(size=9))
    fig.update_yaxes(tickformat=".0%", tickfont=dict(size=9))
    fig.update_annotations(font=dict(size=10))
    fig.update_layout(showlegend=False,
                      margin=dict(l=48, r=20, t=42, b=40),
                      height=190 * rows + 40)
    _apply_theme(fig)
    return fig


def build_position_fan(
    hist_t:           np.ndarray,          # years relative to TODAY (negative)
    hist_line:        np.ndarray,          # realised level, on the payoff's own basket
    bands:            np.ndarray,          # (7, N+1) simulated percentile envelope
    t_grid:           np.ndarray,          # years from today (0 …)
    knock_in_barrier: float,
    obs_labels:       list[tuple[str, float]],
    tr:               Translator,
    autocall_barrier: float | None = None,
    settle_t:         float | None = None,  # years relative to today (negative)
    participation:    bool = False,
) -> go.Figure:
    """A HELD note in one picture: what already happened, then what is left.

    The realised stretch sits at negative time and the simulated envelope opens at
    0. Because both are measured against the SAME original fixings, the realised
    line ends exactly where the envelope begins — no step at the join — so a reader
    sees the whole life instead of a projection that appears from nowhere at today's
    level.

    The web mirror is web/src/components/PathExplorer.tsx:PathFan. It overlays
    sampled paths where this draws percentile bands: a PDF page cannot carry two
    thousand translucent lines legibly, and the envelope says the same thing at
    print resolution.
    """
    hist_t = np.asarray(hist_t, dtype=float) * 12.0
    hist_line = np.asarray(hist_line, dtype=float)
    t_grid = np.asarray(t_grid, dtype=float) * 12.0
    obs_labels = [(lbl, tv * 12.0) for lbl, tv in obs_labels]

    _f_out, _f_mid, _f_in = ((_FILL_OUTERMOST_G, _FILL_OUTER_G, _FILL_INNER_G)
                             if participation else (_FILL_OUTERMOST, _FILL_OUTER, _FILL_INNER))
    fig = go.Figure()
    for lo, hi, fill, key in ((0, 6, _f_out, "pct_1_99"), (1, 5, _f_mid, "pct_5_95"),
                              (2, 4, _f_in, "pct_25_75")):
        fig.add_trace(go.Scatter(
            x=np.concatenate([t_grid, t_grid[::-1]]),
            y=np.concatenate([bands[hi], bands[lo][::-1]]),
            fill="toself", fillcolor=fill,
            line=dict(color="rgba(0,0,0,0)"), name=tr(key)))
    fig.add_trace(go.Scatter(
        x=t_grid, y=bands[3], mode="lines", name=tr("median"),
        line=dict(color=_GREEN if participation else _BLUE, width=2)))
    # Added last so it reads above the envelope: this half is fact, not projection.
    fig.add_trace(go.Scatter(
        x=hist_t, y=hist_line, mode="lines", name=tr("fan_realised"),
        line=dict(color=_INK_LINE, width=2.4)))

    if not participation:
        fig.add_hline(y=knock_in_barrier, line_dash="dash", line_color=_RED,
                      annotation_text=tr("chart_ki_barrier", lvl=f"{knock_in_barrier:.0%}"),
                      annotation_position="bottom right")
        # The barrier must reach back across the realised stretch — it applied then
        # too, and a line starting at today would imply the note was unprotected.
        _add_autocall_barrier(fig, autocall_barrier, None, tr,
                              x0=float(hist_t[0]) if len(hist_t) else 0.0)
    fig.add_vline(x=0.0, line_color=_GREY, line_width=1,
                  annotation_text=tr("fan_today"), annotation_position="top")
    if settle_t is not None and settle_t < -1e-6:
        fig.add_vline(x=float(settle_t) * 12.0, line_dash="dot", line_color=_GREY,
                      line_width=1, annotation_text=tr("fan_bought"),
                      annotation_position="top")
    for label, t_val in obs_labels:
        fig.add_vline(x=t_val, line_dash="dot", line_color="#aaa",
                      annotation_text=label, annotation_position="top")

    fig.update_layout(
        xaxis=dict(title=tr("time_months"), tickformat=".0f"),
        yaxis=dict(title=tr("perf_vs_initial"), tickformat=".0%"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
        margin=dict(l=60, r=30, t=50, b=78),
    )
    _apply_theme(fig)
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
        # Max redemption = 1 + rate·upside_cap (the cap is on the underlying move).
        _rate = float(getattr(terms, "participation_rate", 1.0) or 1.0)
        _ref((1.0 + _rate * terms.upside_cap) * 100.0, "#9ca3af", tr("lbl_cap"))

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


def _bin_edges(*arrays, n_bins: int = 60) -> np.ndarray:
    """Shared bin edges spanning every array, so overlaid distributions line up."""
    lo = float(min(float(np.min(a)) for a in arrays))
    hi = float(max(float(np.max(a)) for a in arrays))
    size = max((hi - lo) / n_bins, 1e-6)
    return np.arange(lo, hi + size * 1.5, size)


def _pct_bar(values, edges, name, color, tr_fmt: str, *, denom: int | None = None,
             opacity: float = 0.55) -> go.Bar:
    """A pre-binned histogram bar trace.

    go.Histogram would ship EVERY raw value to the browser — at 20 000 antithetic
    paths that is hundreds of KB per trace for a picture with 60 bars. Binning
    server-side sends the 60 bars instead, pixel-identical. `denom` normalises
    against a different total (e.g. both halves of a signed split) so the areas
    stay comparable; default is the trace's own count, matching histnorm="percent".
    """
    v = np.asarray(values, dtype=float)
    counts, _ = np.histogram(v, bins=edges)
    total = denom if denom else max(int(counts.sum()), 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    return go.Bar(
        x=np.round(centers, 4), y=np.round(counts / total * 100.0, 4),
        name=name, marker_color=color, opacity=opacity, marker_line_width=0,
        width=float(edges[1] - edges[0]),
        hovertemplate=f"{name}: {tr_fmt}<extra></extra>")


def _cmp_buckets(note) -> tuple[list[str], list[np.ndarray]]:
    """The three economic outcomes, as boolean masks over a note's paths — the
    same split `_build_irr_discrete` uses, so A/B reads like the Monte Carlo."""
    irr = np.asarray(note["annualized_returns"], dtype=float)
    ac = np.asarray(note.get("autocall_events", note.get("autocall_period")), dtype=int)
    loss = irr < 0
    called = (ac > 0) & ~loss
    return ["chart_irr_bucket_autocall", "chart_irr_bucket_maturity", "chart_irr_bucket_loss"], \
           [called, ~called & ~loss, loss]


def build_irr_compare(note_a, note_b, tr: Translator) -> go.Figure:
    """A vs B as a DISCRETE outcome breakdown, not overlaid histograms.

    Same reasoning as `build_irr_distribution`: a structured note concentrates
    almost all of its mass on a handful of outcomes, so a continuous histogram
    collapses into one spike in an empty grid and reads as a render glitch. One
    grouped pair of bars per outcome instead — panel 1 how likely it is under
    each note, panel 2 what it pays under each."""
    keys, masks_a = _cmp_buckets(note_a)
    _, masks_b = _cmp_buckets(note_b)
    labels = [tr(k) for k in keys]
    na, nb = len(masks_a[0]), len(masks_b[0])
    tot_a = np.asarray(note_a["total_returns"], dtype=float)
    tot_b = np.asarray(note_b["total_returns"], dtype=float)

    # Drop outcomes neither note ever reaches — no empty bars in an empty grid.
    keep = [i for i in range(3) if masks_a[i].any() or masks_b[i].any()]
    labels = [labels[i] for i in keep]
    p_a = [float(masks_a[i].sum()) / na for i in keep]
    p_b = [float(masks_b[i].sum()) / nb for i in keep]
    r_a = [float(tot_a[masks_a[i]].mean()) if masks_a[i].any() else 0.0 for i in keep]
    r_b = [float(tot_b[masks_b[i]].mean()) if masks_b[i].any() else 0.0 for i in keep]

    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.16,
                        subplot_titles=[tr("chart_disc_prob_panel"), tr("cmp_mean_return_panel")])
    for col, (va, vb, fmt) in enumerate(((p_a, p_b, "{:.1%}"), (r_a, r_b, "{:+.1%}")), start=1):
        for vals, name, color in ((va, tr("cmp_note_a"), _CMP_A), (vb, tr("cmp_note_b"), _CMP_B)):
            fig.add_trace(go.Bar(
                x=labels, y=vals, name=name, marker_color=color, marker_line_width=0,
                text=[fmt.format(v) for v in vals], textposition="outside",
                cliponaxis=False, textfont=dict(size=11),
                legendgroup=name, showlegend=(col == 1),
                hovertemplate=f"{name} · %{{x}}: %{{y:.1%}}<extra></extra>",
            ), row=1, col=col)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.12], row=1, col=1)
    _vals = r_a + r_b
    lo, hi = min(0.0, min(_vals)), max(0.0, max(_vals))
    pad = (hi - lo) * 0.22 or 0.05
    fig.update_yaxes(tickformat=".0%", range=[lo - pad, hi + pad], row=1, col=2)
    fig.update_xaxes(type="category")
    fig.update_layout(
        title=tr("cmp_irr_dist"), barmode="group", bargap=0.28, bargroupgap=0.08,
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5,
                    bgcolor="rgba(0,0,0,0)"),
    )
    _apply_theme(fig)
    fig.update_layout(margin=dict(l=52, r=24, t=62, b=62))
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
        edges = _bin_edges(A, B)
        fig = go.Figure()
        for x, name, color in ((A, tr("cmp_note_a"), _CMP_A), (B, tr("cmp_note_b"), _CMP_B)):
            fig.add_trace(_pct_bar(x, edges, name, color, "%{x:.0f}%"))
        fig.add_vline(x=100.0, line=dict(color="#6b7280", width=1.5, dash="dash"))
        fig.update_layout(
            title=tr("cmp_redemption"), barmode="overlay", bargap=0,
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
        # Deliberately far apart in hue AND lightness: a brand palette can push
        # two "nearby" colours together until the legend is unreadable, which is
        # exactly what a blue/green pair did here.
        for name, frac, color, grp in (
            (tr("autocalled_early"), ac, "#1d4ed8", "ac"),      # deep blue
            (tr("redeemed_at_par"), redeemed, "#0d9488", "par"),  # teal
            (tr("knocked_in"), ki, "#dc2626", "ki"),             # red
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


# ---------------------------------------------------------------------------
# A/B paired analytics — only meaningful when both notes priced the SAME paths
# ---------------------------------------------------------------------------
# Path i means the same thing for A and B, so the per-path DIFFERENCE is a real
# quantity rather than a difference of two independent averages. These builders
# visualise that difference; api/engine.py:_paired_stats computes the numbers.

def build_paired_delta(note_a, note_b, tr: Translator) -> go.Figure:
    """WHERE B's edge comes from: the mean per-path edge (B − A) within each of
    A's outcomes, with how often B wins inside that outcome.

    A histogram of the edge has the same failure as a histogram of the IRR — the
    edge is near-constant on the paths that autocall, so the mass piles into one
    or two spikes. Bucketing by outcome says the useful thing instead: whether B
    is better in the good states, the bad ones, or across the board."""
    keys, masks = _cmp_buckets(note_a)
    ta = np.asarray(note_a["total_returns"], dtype=float)
    tb = np.asarray(note_b["total_returns"], dtype=float)
    d = tb - ta
    keep = [i for i in range(3) if masks[i].any()]
    labels = [tr(keys[i]) for i in keep]
    edges = [float(d[masks[i]].mean()) for i in keep]
    wins = [float((d[masks[i]] > 1e-12).mean()) for i in keep]
    share = [float(masks[i].mean()) for i in keep]
    # Colour by who the edge favours, so the direction reads before the number.
    colors = [_CMP_B if e >= 0 else _CMP_A for e in edges]

    fig = go.Figure(go.Bar(
        x=labels, y=edges, marker_color=colors, marker_line_width=0, width=0.5,
        text=[f"{e:+.2%}" for e in edges], textposition="outside",
        cliponaxis=False, textfont=dict(size=12), showlegend=False,
        customdata=np.column_stack([wins, share]),
        hovertemplate=(f"%{{x}}<br>{tr('cmp_edge_hover')}: %{{y:+.2%}}"
                       f"<br>{tr('cmp_win_rate')}: %{{customdata[0]:.0%}}"
                       f"<br>{tr('cmp_share_hover')}: %{{customdata[1]:.0%}}<extra></extra>")))
    fig.add_hline(y=0.0, line=dict(color=_GREY, width=1.2))
    lo, hi = min(0.0, min(edges)), max(0.0, max(edges))
    pad = (hi - lo) * 0.26 or 0.02
    fig.update_layout(
        title=tr("cmp_delta_title"),
        xaxis=dict(title=tr("cmp_outcome_axis"), type="category"),
        yaxis=dict(title=tr("cmp_delta_axis"), tickformat=".0%", range=[lo - pad, hi + pad]),
        bargap=0.4)
    _apply_theme(fig)
    fig.update_layout(margin=dict(l=58, r=24, t=52, b=56))
    return fig


def build_paired_scatter(a_vals, b_vals, tr: Translator, *, max_points: int = 2500) -> go.Figure:
    """Per-path A vs B IRR with a 45° reference. Points above the line are paths
    where B won — so the SHAPE shows whether B's edge comes from the good states,
    the bad states, or uniformly, which no pair of summary means can tell you.
    Stride-subsampled (paths are unordered) to keep the payload sane."""
    A = np.asarray(a_vals, dtype=float) * 100.0
    B = np.asarray(b_vals, dtype=float) * 100.0
    stride = max(1, len(A) // max_points)
    # 2 dp is finer than a plotted pixel at any realistic axis range, and cuts the
    # serialised payload several-fold versus full float64 repr.
    A = np.round(A[::stride][:max_points], 2)
    B = np.round(B[::stride][:max_points], 2)
    # Clip to the 1st–99th percentile of the union. A handful of deep knock-in
    # paths otherwise stretch the axes so far that the bulk of the cloud is a dot
    # in the corner — the same failure the histograms had.
    both = np.concatenate([A, B])
    lo = float(np.percentile(both, 1)); hi = float(np.percentile(both, 99))
    if hi - lo < 1e-9:
        lo, hi = lo - 1.0, hi + 1.0
    pad = max((hi - lo) * 0.06, 0.5)
    lo, hi = lo - pad, hi + pad
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[lo, hi], y=[lo, hi], mode="lines", name=tr("cmp_parity"),
        line=dict(color=_GREY, width=1.2, dash="dash"), hoverinfo="skip"))
    win = B > A
    for mask, name, color in ((~win, tr("cmp_a_wins"), _CMP_A), (win, tr("cmp_b_wins"), _CMP_B)):
        if not mask.any():
            continue
        fig.add_trace(go.Scatter(
            x=A[mask], y=B[mask], mode="markers", name=name,
            marker=dict(size=4, color=color, opacity=0.45, line=dict(width=0)),
            hovertemplate=f"A %{{x:.1f}}% · B %{{y:.1f}}%<extra>{name}</extra>"))
    fig.update_layout(
        title=tr("cmp_scatter_title"),
        xaxis=dict(title=tr("cmp_scatter_x"), ticksuffix="%", range=[lo, hi]),
        yaxis=dict(title=tr("cmp_scatter_y"), ticksuffix="%", range=[lo, hi],
                   scaleanchor="x", scaleratio=1),
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5,
                    bgcolor="rgba(0,0,0,0)"))
    _apply_theme(fig)
    fig.update_layout(margin=dict(l=56, r=24, t=52, b=64))
    return fig


def build_transition_heatmap(matrix, labels: list[str], tr: Translator) -> go.Figure:
    """How each path resolves under A (rows) vs under B (columns). The diagonal is
    'same outcome either way'; everything off it is a path the swap actually moved
    — e.g. the cell that answers "of the paths where A knocked in, what did B do?"."""
    m = np.asarray(matrix, dtype=float)
    txt = [[f"{v:.1%}" if v >= 0.0005 else "" for v in row] for row in m]
    # A tint of the A-series colour rather than white→navy: the low end is
    # near-transparent so the page (light OR dark) shows through instead of a
    # white slab, and the top stop stays light enough that the cell figure —
    # which inherits the surface's text colour — reads on it either way. Both
    # literals are in the web's SERIES_REMAP, so the ramp follows the theme.
    fig = go.Figure(go.Heatmap(
        z=m, x=labels, y=labels, text=txt, texttemplate="%{text}",
        colorscale=[[0, "rgba(37,99,235,0.04)"], [1, "rgba(37,99,235,0.40)"]],
        zmin=0.0, showscale=False, xgap=3, ygap=3,
        # Explicit, or Plotly auto-contrasts each cell against a WHITE canvas and
        # picks dark text — invisible once the page behind is dark. _NAVY is the
        # ink/primary literal every surface already remaps: brand primary in the
        # PDF, ink in light mode, the light text colour in dark mode.
        textfont=dict(color=_NAVY, size=11),
        hovertemplate=(f"{tr('cmp_note_a')}: %{{y}}<br>{tr('cmp_note_b')}: %{{x}}"
                       "<br>%{z:.2%}<extra></extra>")))
    fig.update_layout(
        title=tr("cmp_transition_title"),
        xaxis=dict(title=tr("cmp_note_b"), side="bottom"),
        yaxis=dict(title=tr("cmp_note_a"), autorange="reversed"))
    _apply_theme(fig)
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    fig.update_layout(margin=dict(l=52, r=24, t=52, b=52))
    return fig


def build_wof_fan_compare(bands_a, bands_b, t_grid, knock_in, tr: Translator,
                          *, autocall_barrier=None, shared: bool = False,
                          knock_in_b=None, autocall_barrier_b=None) -> go.Figure:
    """Worst-of envelopes with each note's barriers drawn across them.

    The envelope is a property of the SIMULATION, not of the note. When the paths
    are shared, A's and B's are the same array — plotting both drew one curve
    exactly on top of the other and stacked two translucent bands into an opaque
    slab. So when `shared`, draw the market once (neutral) and let the barriers
    carry the comparison: where each note's knock-in and autocall sit relative to
    the same distribution IS the difference. Two envelopes only when the notes
    ran different simulations, which is the case where they actually differ.
    """
    t = np.asarray(t_grid, dtype=float) * 12.0        # months
    fig = go.Figure()
    # The shared envelope's band uses the blue-family rgba literal (→ viridian
    # tint on the web, brand accent in the PDF): a literal grey rgba is in no
    # remap table, so it stayed a flat slab of grey on a dark page.
    series = ([(bands_a, tr("cmp_market_envelope"), _GREY, "rgba(37,99,235,0.08)")] if shared else
              [(bands_a, tr("cmp_note_a"), _CMP_A, None),
               (bands_b, tr("cmp_note_b"), _CMP_B, None)])
    for bands, name, color, fill_override in series:
        if bands is None:
            continue
        # 4 dp on a 0–3 performance scale is well under a plotted pixel; full
        # float64 repr would triple the serialised size for no visible gain.
        b = np.round(np.asarray(bands, dtype=float), 4)   # (7, N+1) → [1,5,25,50,75,95,99]
        rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        fill = fill_override or f"rgba({rgb[0]},{rgb[1]},{rgb[2]},0.13)"
        fig.add_trace(go.Scatter(x=t, y=b[4], mode="lines", line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=t, y=b[2], mode="lines", line=dict(width=0),
                                 fill="tonexty", fillcolor=fill,
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(
            x=t, y=b[3], mode="lines", name=name, line=dict(color=color, width=2.2),
            hovertemplate=f"{name} · %{{x:.0f}}mo: %{{y:.1%}}<extra></extra>"))

    # Barrier lines, tagged with the note they belong to whenever the two differ
    # — labelling a single "Knock-in barrier 50%" while B's sits at 60% is worse
    # than no label at all.
    def _levels(a, b):
        """[(level, suffix)] — one entry when they agree, one per note when not."""
        if a is None:
            return []
        if b is None or abs(float(a) - float(b)) < 1e-9:
            return [(float(a), "")]
        return [(float(a), f" · {tr('cmp_note_a')}"), (float(b), f" · {tr('cmp_note_b')}")]

    for lvl, tag in _levels(knock_in, knock_in_b):
        # Above the line, not below: the lower of two knock-ins sits near the
        # bottom of the range, and a label under it is clipped by the plot edge.
        fig.add_hline(y=lvl, line_dash="dash", line_color=_RED,
                      annotation_text=tr("chart_ki_barrier", lvl=f"{lvl:.0%}") + tag,
                      annotation_position="top right")
    for lvl, tag in _levels(autocall_barrier, autocall_barrier_b):
        fig.add_hline(y=lvl, line_dash="dot", line_color=_GREY,
                      annotation_text=tr("chart_autocall_barrier_lvl", lvl=f"{lvl:.0%}") + tag,
                      annotation_position="top right")
    fig.update_layout(
        title=tr("cmp_fan_title"),
        xaxis=dict(title=tr("time_months"), tickformat=".0f"),
        yaxis=dict(title=tr("perf_vs_initial"), tickformat=".0%"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5,
                    bgcolor="rgba(0,0,0,0)"))
    _apply_theme(fig)
    # Rotated y-axis title needs more room than the shared default, or it clips.
    fig.update_layout(margin=dict(l=76, r=24, t=52, b=64))
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
            # Left, not right: the outcome legend sits along the right edge and
            # a right-anchored annotation prints on top of its first entries.
            fig.add_hline(y=0, line_dash="dash", line_color=_GREY,
                          annotation_text=tr("break_even"),
                          annotation_position="top left")
    else:
        fig.add_hline(
            y=0, line_dash="dash", line_color=_GREY,
            annotation_text=tr("break_even"),
            annotation_position="top left",
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

def _add_settlement_line(fig, settlement_date, dates, tr) -> None:
    """Mark where a secondary-market position settled. No-op when the caller
    passes None (held from issue) or the date falls outside the plotted window."""
    if settlement_date is None or len(dates) == 0:
        return
    s = pd.Timestamp(settlement_date)
    if not (dates[0] <= s <= dates[-1]):
        return
    fig.add_vline(x=s.isoformat(), line_dash="dashdot", line_color="#7c3aed",
                  line_width=2, annotation_text=tr("chart_settlement"),
                  annotation_position="bottom left")


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
    settlement_date:    pd.Timestamp | None = None,
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

    # Where the current holder bought in — only drawn for a secondary-market
    # position (the caller passes None when the note was held from issue, since a
    # settlement line on the issue date is just noise).
    _add_settlement_line(fig, settlement_date, dates, tr)

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
    settlement_date: pd.Timestamp | None = None,
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

    _add_settlement_line(fig, settlement_date, dates, tr)

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