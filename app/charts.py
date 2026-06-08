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
    build_call_prob_curve, build_payoff_distribution,
    build_fan_chart, build_wof_fan, build_corr_heatmaps,
    build_backtest_irr_scatter, build_backtest_outcome_bar,
    build_worst_asset_pie, build_historical_prices, build_wof_rolling,
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

_OUTCOME_COLORS = {
    # keys are English labels — caller maps translated labels to these
    "Called at 3M":  _GREEN_LIGHT,
    "Called at 6M":  _GREEN_MID,
    "Called at 9M":  _GREEN_DARK,
    "Maturity":      "#3498db",
    "Floor Applied": "#e74c3c",
}


def _plain_layout(fig: go.Figure) -> go.Figure:
    fig.update_layout(plot_bgcolor=_WHITE, paper_bgcolor=_WHITE)
    return fig


# ---------------------------------------------------------------------------
# Sidebar — issuer call probability curve
# ---------------------------------------------------------------------------

def build_call_prob_curve(
    floor_level:    float,
    call_steepness: float,
    tr:             Translator,
) -> go.Figure:
    perf = np.linspace(0.80, 1.20, 300)
    prob = 1.0 / (1.0 + np.exp(-call_steepness * (perf - floor_level)))
    prob[perf < floor_level] = 0.0

    fig = px.line(
        pd.DataFrame({
            tr("worst_of_perf_axis"): perf,
            tr("p_issuer_calls"):     prob,
        }),
        x=tr("worst_of_perf_axis"),
        y=tr("p_issuer_calls"),
    )
    fig.add_vline(
        x=floor_level,
        line_dash="dash",
        line_color=_GREEN_MID,
        annotation_text=f"Call Strike ({floor_level:.0%})",
        annotation_position="top right",
    )
    fig.update_layout(
        yaxis=dict(tickformat=".0%", range=[0, 1.05]),
        xaxis=dict(tickformat=".0%"),
        height=280,
        margin=dict(t=10, b=20),
    )
    return _plain_layout(fig)


# ---------------------------------------------------------------------------
# Tab 1 — payoff profile + terminal distribution
# ---------------------------------------------------------------------------

def build_payoff_distribution(
    worst_of_paths: np.ndarray,
    autocall_events: np.ndarray,
    floor_level:    float,
    N:              int,
    tr:             Translator,
) -> go.Figure:
    worst_perf_grid = np.linspace(0.50, 1.50, 500)
    payoff_grid     = np.where(worst_perf_grid < floor_level, floor_level, worst_perf_grid)

    terminal_worst = worst_of_paths[autocall_events == 0, N]
    fig = go.Figure()

    if len(terminal_worst) > 0:
        fig.add_trace(go.Histogram(
            x=terminal_worst,
            nbinsx=60,
            name=tr("simulated_terminal"),
            yaxis="y2",
            opacity=0.4,
            marker_color=_GREEN_MID,
            histnorm="probability",
        ))

    fig.add_trace(go.Scatter(
        x=worst_perf_grid,
        y=payoff_grid,
        mode="lines",
        name=tr("contractual_payoff"),
        line=dict(color=_GREEN_DARK, width=2.5),
    ))

    fig.add_vline(
        x=floor_level,
        line_dash="dash",
        line_color="#4a7a4a",
        annotation_text=f"Floor / Call Strike ({floor_level:.0%})",
        annotation_position="top right",
    )

    fig.update_layout(
        xaxis=dict(title=tr("worst_of_final_perf"),  tickformat=".0%"),
        yaxis=dict(title=tr("note_payoff"),           tickformat=".0%"),
        yaxis2=dict(
            title=tr("prob_maturity_paths"),
            overlaying="y",
            side="right",
            showgrid=False,
            tickformat=".1%",
        ),
        legend=dict(x=0.01, y=0.99),
        hovermode="x unified",
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
    worst_of_paths: np.ndarray,
    t_grid:         np.ndarray,
    floor_level:    float,
    obs_labels:     list[tuple[float, str]],
    tr:             Translator,
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
        y=floor_level, line_dash="dash", line_color=_RED,
        annotation_text=f"Floor / Call Strike ({floor_level:.0%})",
        annotation_position="bottom right",
    )
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
    worst_path:      np.ndarray,
    autocall_q:      int,
    obs_steps:       list[int],
    obs_labels:      list[str],
    floor_level:     float,
    path_num:        int,
    tr:              Translator,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=worst_path, mode="lines",
        name=tr("worst_of_perf_axis"),
        line=dict(color=_GREEN_MID, width=2),
    ))
    fig.add_hline(
        y=floor_level, line_dash="dash", line_color=_RED,
        annotation_text=f"Call Strike / Floor ({floor_level:.0%})",
        annotation_position="bottom right",
    )
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
    maturity_bt = bt[bt["Call Quarter"] == 0]
    if maturity_bt.empty:
        return go.Figure()

    wc = maturity_bt["Worst Asset"].value_counts().reset_index()
    wc.columns = [tr("asset"), tr("count")]
    fig = px.pie(
        wc,
        names=tr("asset"),
        values=tr("count"),
        title=tr("worst_asset_at_mat"),
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
    colors = {"SPX": _GREEN_MID, "SX5E": _GREEN_LIGHT, "SMI": _GREEN_DARK}
    fig = go.Figure()
    for col in hist_prices.columns:
        normed = hist_prices[col] / hist_prices[col].iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=hist_prices.index, y=normed,
            mode="lines", name=col,
            line=dict(color=colors.get(col, _GREY), width=1.5),
        ))
    fig.add_vline(x=bt_start, line_dash="dot", line_color=_GREY,
                  annotation_text=tr("backtest_start"), annotation_position="top right")
    fig.add_vline(x=bt_end,   line_dash="dot", line_color=_GREY,
                  annotation_text=tr("backtest_end"),   annotation_position="top left")
    fig.update_layout(
        xaxis=dict(title=tr("date_axis")),
        yaxis=dict(title=tr("normalised_level")),
        hovermode="x unified",
        legend=dict(x=0.01, y=0.99),
    )
    return _plain_layout(fig)


# ---------------------------------------------------------------------------
# Backtest — rolling worst-of performance
# ---------------------------------------------------------------------------

def build_wof_rolling(
    hist_prices: pd.DataFrame,
    floor_level: float,
    tr:          Translator,
) -> go.Figure:
    prices_arr   = hist_prices.values
    dates        = hist_prices.index
    window       = 252
    rolling_worst = []
    rolling_dates = []
    for i in range(window, len(prices_arr)):
        perf = prices_arr[i] / prices_arr[i - window]
        rolling_worst.append(perf.min())
        rolling_dates.append(dates[i])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rolling_dates, y=rolling_worst,
        mode="lines", name=tr("wof_1y_rolling"),
        line=dict(color=_GREEN_MID, width=1.5),
        fill="tozeroy", fillcolor="rgba(26,107,26,0.08)",
    ))
    fig.add_hline(
        y=floor_level, line_dash="dash", line_color=_RED,
        annotation_text=f"Floor / Call Strike ({floor_level:.0%})",
        annotation_position="bottom right",
    )
    fig.add_hline(
        y=1.0, line_dash="dot", line_color=_GREY,
        annotation_text=tr("no_change"), annotation_position="top right",
    )
    fig.update_layout(
        xaxis=dict(title=tr("date_axis")),
        yaxis=dict(title=tr("perf_vs_initial"), tickformat=".0%"),
        hovermode="x unified",
    )
    return _plain_layout(fig)