"""
app/translations.py
-------------------
All user-facing strings in one place.

Usage
-----
from app.translations import Translator

tr = Translator(lang="en")   # or"es"
tr("run_simulation")         # → "Run Simulation"
tr("run_simulation", "es") # → "Ejecutar Simulación" (override)
"""

from __future__ import annotations

_STRINGS: dict[str, tuple[str, str]] = {
    # ── Sidebar ────────────────────────────────────────────────────────────
    "run_simulation":           ("Run Simulation",               "Ejecutar Simulación"),

    # ── Page title / intro ─────────────────────────────────────────────────
    "page_title":               ("Multi-Asset Structured Note Simulator",
                                 "Simulador de Notas Estructuradas Multi-Activo"),

    # ── Expander ───────────────────────────────────────────────────────────

    # ── Summary stats ──────────────────────────────────────────────────────
    "sim_complete":             ("Simulation complete.",             "Simulación completada."),

    # ── Tab labels ─────────────────────────────────────────────────────────

    # ── Tab 1 — Payoff ─────────────────────────────────────────────────────

    # ── Tab 2 — Fan ────────────────────────────────────────────────────────
    "simulated_price_dist":     ("Simulated Price Distribution",     "Distribución de Precios Simulados"),
    "time_years":               ("Time (years)",                     "Tiempo (años)"),
    "price":                    ("Price",                            "Precio"),
    "median":                   ("Median",                           "Mediana"),
    "pct_1_99":                 ("1st–99th pct",                     "Pct 1–99"),
    "pct_5_95":                 ("5th–95th pct",                     "Pct 5–95"),
    "pct_25_75":                ("25th–75th pct",                    "Pct 25–75"),
    "perf_vs_initial":          ("Performance vs Initial",           "Rendimiento vs Inicial"),

    # ── Tab 3 — Path Explorer ──────────────────────────────────────────────
    "asset_price_paths":        ("Asset Price Paths — Path #{n}",   "Trayectorias de Precios — Trayectoria #{n}"),
    "price_label":              ("Price",                            "Precio"),
    "time_step":                ("Time Step",                        "Paso de Tiempo"),
    "wof_path_title":           ("Worst-of Performance Path #{n}",  "Trayectoria Worst-of #{n}"),
    "called_label":             ("← Called",                        "← Rescatada"),
    "continued_label":          ("(continued)",                     "(continúa)"),
    "coupon_paid_label":        ("coupon paid",                     "cupón pagado"),
    "coupon_missed_label":      ("no coupon",                       "sin cupón"),
    # Richer path-explorer legend statuses
    "leg_called":               ("Autocalled",                      "Autocancelada"),
    "leg_maturity":             ("Maturity",                        "Vencimiento"),
    "leg_knock_in":             ("knock-in · capital loss",         "knock-in · pérdida de capital"),
    "leg_no_knock_in":          ("no knock-in · redeemed at par",   "sin knock-in · reembolso a la par"),
    "leg_wof":                  ("worst-of {v}",                    "worst-of {v}"),
    "leg_coupon":               ("coupon {v}",                      "cupón {v}"),
    "leg_coupon_memory":        ("coupon {v} (memory ×{k})",        "cupón {v} (memoria ×{k})"),
    "leg_no_coupon":            ("no coupon",                       "sin cupón"),
    "leg_no_coupon_pending":    ("no coupon ({k} pending)",         "sin cupón ({k} pendiente(s))"),
    "leg_premium":              ("premium {v} ({k} periods accrued)", "prima {v} ({k} períodos acumulados)"),
    "leg_accruing":             ("premium accruing",                "prima acumulándose"),
    "leg_one_star":             ("★ one-star rescue",               "★ rescate one-star"),
    "leg_redeemed_par":         ("redeemed at par",                 "reembolso a la par"),
    "explorer_panel_name":      ("Panel name (chart title)",        "Nombre del panel (título)"),
    "explorer_panel_name_ph":   ("e.g. Best autocall scenario",     "p. ej. Mejor escenario de autocall"),

    # ── Tab 4 — Correlation ────────────────────────────────────────────────
    "asset":                    ("Asset",                            "Activo"),

    # ── Note structure expander ────────────────────────────────────────────
    "note_structure_expander": ("Note Structure Summary",         "Resumen de la Estructura de la Nota"),
    "underlyings_header":        ("**Underlyings**",                   "**Subyacentes**"),
    "col_display_name":          ("Display Name",                      "Nombre"),

    # ── Underlying breakdown (note structure expander + setup) ─────────────
    "ul_breakdown_header":   ("**Underlying Breakdown**",          "**Análisis por Subyacente**"),
    "ul_market_cap":         ("Market cap",                        "Capitalización"),
    "ul_iv_3m":              ("3M ATM implied vol",                "Vol. implícita ATM 3M"),
    "ul_vol_3m_realized":    ("3M realized vol",                   "Vol. realizada 3M"),
    "ul_iv_3m_help":         ("At-the-money implied volatility — strike nearest spot "
                              "(~100% moneyness), call & put averaged, expiry nearest +90 days.",
                              "Volatilidad implícita at-the-money — strike más cercano al spot "
                              "(~100% de moneyness), promedio de call y put, vencimiento más próximo a +90 días."),
    "ul_vol_3m_realized_help": ("No listed options on Yahoo — annualised standard deviation of "
                              "daily log-returns over the last ~63 trading days (≈3M).",
                              "Sin opciones listadas en Yahoo — desviación estándar anualizada de los "
                              "log-retornos diarios de los últimos ~63 días hábiles (≈3M)."),
    "ul_last_price":         ("Last price",                        "Último precio"),
    "ul_rsi":                ("RSI (14)",                          "RSI (14)"),
    "ul_sector":             ("Sector",                            "Sector"),
    "ul_type":               ("Type",                              "Tipo"),
    "ul_price_1y":           ("Trailing 12-month price",           "Precio últimos 12 meses"),
    "ul_loading":            ("Loading underlying market data…",   "Cargando datos de mercado…"),
    "ul_metrics_failed":     ("Could not load underlying market data.",
                              "No se pudieron cargar los datos de mercado."),
    "setup_ul_descriptions": ("Underlying descriptions",           "Descripciones de subyacentes"),
    "setup_ul_desc_help":    ("Optional company blurb shown in the Underlying Breakdown — preloaded from the note config, like the issuer description.",
                              "Texto opcional de la empresa, mostrado en el Análisis por Subyacente — precargado desde la configuración, como la descripción del emisor."),
    "setup_ul_prefill":      ("Prefill from Yahoo",                "Rellenar desde Yahoo"),
    "setup_ul_prefill_help": ("Fetch the company business summary from Yahoo Finance into the box above.",
                              "Obtener el resumen de la empresa de Yahoo Finance en el cuadro de arriba."),
    "setup_ul_prefill_spinner": ("Fetching summary from Yahoo…", "Obteniendo resumen de Yahoo…"),
    "ul_translate_unavailable": ("Couldn't translate to Spanish — kept the English text. (Is deep-translator installed?)",
                                 "No se pudo traducir al español — se mantuvo el texto en inglés. (¿Está instalado deep-translator?)"),
    "col_yf_symbol":             ("yfinance Symbol",                   "Símbolo yfinance"),
    "metric_maturity":           ("Maturity",                          "Vencimiento"),
    "metric_observations":       ("Observations",                      "Observaciones"),
    "metric_frequency":          ("Frequency",                         "Frecuencia"),
    "metric_coupon_pa":          ("Coupon p.a.",                       "Cupón anual"),
    "metric_coupon_period":      ("Coupon / period",                   "Cupón / período"),
    "metric_memory":             ("Memory",                            "Memoria"),
    "metric_coupon_barrier":     ("Coupon barrier",                    "Barrera de cupón"),
    "metric_autocall_barrier":   ("Autocall barrier",                  "Barrera autocall"),
    "metric_ki_barrier":         ("Knock-in barrier",                  "Barrera knock-in"),
    "yes":                       ("Yes",                               "Sí"),
    "no_str":                    ("No",                                "No"),
    "col_period":                ("Period",                            "Período"),
    "col_time_y":                ("Time (Y)",                          "Tiempo (A)"),
    "col_autocall_eligible":     ("Autocall eligible",                 "Elegible autocall"),
    "one_star_info":             (
        "**One Star ({barrier:.0%}):** a single underlying at or above {barrier:.0%} of initial "
        "pays the coupon, triggers the autocall, and returns capital at par at maturity — "
        "even if the worst performer is below its barrier or the knock-in was breached.",
        "**One Star ({barrier:.0%}):** un único subyacente en o por encima del {barrier:.0%} del inicial "
        "paga el cupón, dispara el autocall y devuelve el capital a la par al vencimiento — "
        "incluso si el peor subyacente está por debajo de su barrera o se tocó el knock-in.",
    ),

    # ── MC tab — top-level ─────────────────────────────────────────────────
    "summary_stats_header":      ("Summary Statistics",                "Estadísticas Resumen"),
    "summary_returns_label":     ("Expected return",                   "Retorno esperado"),
    "summary_risk_label":        ("Risk & protection",                 "Riesgo y protección"),
    "expected_irr_pa":           ("Expected IRR p.a. (simple)",        "TIR Esperada p.a. (simple)"),
    "expected_total_return":     ("Expected Total Return",             "Rendimiento Total Esperado"),
    "expected_coupon_metric":    ("Expected Coupon",                   "Cupón Esperado"),
    "prob_autocalled":           ("P(Autocalled)",                     "P(Autocall)"),
    "prob_knock_in_metric":      ("P(knock-in)",                       "P(knock-in)"),
    "loss_given_ki_metric":      ("Loss given knock-in",               "Pérdida dado knock-in"),
    "barrier_rescued_caption":   (
        "Barrier breached on {barrier:.2%} of paths; {rescued:.2%} were rescued to par by the"
        "One Star condition (best-of ≥ {level:.0%}).",
        "Barrera tocada en el {barrier:.2%} de trayectorias; {rescued:.2%} fueron rescatadas a la par por"
        "la condición One Star (mejor de ≥ {level:.0%}).",
    ),
    "autocall_by_period_expander": ("Autocall probability by period", "Probabilidad de autocall por período"),
    "col_eligible":              ("Eligible",                          "Elegible"),
    "col_p_autocall":            ("P(autocall)",                       "P(autocall)"),

    # ── MC sub-tabs ────────────────────────────────────────────────────────
    "mc_subtab_summary":         ("Summary",                        "Resumen"),
    "mc_subtab_payoff":          ("Payoff & Distribution",          "Payoff y Distribución"),
    "mc_subtab_paths":           ("Price Paths",                    "Trayectorias de Precio"),
    "mc_subtab_explorer":        ("Path Explorer",                  "Explorador de Trayectorias"),
    "mc_subtab_corr":            ("Correlation Diagnostics",        "Diagnóstico de Correlaciones"),
    "pdf_include_toggle":        ("Include this analysis in the PDF report",
                                  "Incluir este análisis en el informe PDF"),
    "pdf_include_help":          ("When checked, this section is written to the generated PDF. Uncheck to build a custom report without it.",
                                  "Si está marcado, esta sección se escribe en el PDF generado. Desmárquelo para crear un informe personalizado sin ella."),
    "bt_subtab_outcomes":        ("Outcomes & Summary",             "Resultados y Resumen"),
    "bt_subtab_prices":          ("Price History",                  "Histórico de Precios"),
    "bt_subtab_explorer":        ("Path Explorer",                  "Explorador de Trayectorias"),

    # ── MC tab1 — IRR distribution ─────────────────────────────────────────
    "irr_dist_subheader":        ("IRR Distribution — All Simulated Paths",
                                  "Distribución de TIR — Todas las Trayectorias Simuladas"),
    "knock_in_info":             (
        "**{pct:.1%}** of paths knock in at maturity — worst-of below the {barrier:.0%} barrier and not rescued by the final redemption clause.",
        "**{pct:.1%}** de las trayectorias hacen knock-in al vencimiento — worst-of bajo la barrera del {barrier:.0%} y no rescatadas por la condición de redención final.",
    ),

    # ── MC tab2 — price paths ──────────────────────────────────────────────
    "price_paths_subheader":     ("Simulated Price Path Fan Charts",   "Abanicos de Trayectorias de Precio Simuladas"),
    "wof_basket_md":             ("#### Worst-of Performance",  "#### Rendimiento Worst-of"),
    "individual_paths_md":       ("#### Individual Underlying Paths",  "#### Trayectorias Individuales de Subyacentes"),

    # ── MC tab3 — path explorer ────────────────────────────────────────────
    "single_path_subheader":     ("Single Path Explorer",              "Explorador de Trayectoria Individual"),
    "path_caption":              ("Path #{n} of {total}",              "Trayectoria #{n} de {total}"),
    # ── Path-explorer filter + multi-panel comparison ───────────────────────
    "explorer_intro_caption":    ("Filter the simulated paths down to the scenarios you care about, then step through the matches. Add a panel to compare two queries side by side.",
                                  "Filtra las trayectorias simuladas a los escenarios que te interesan y recórrelas. Añade un panel para comparar dos consultas."),
    "explorer_add_panel":        ("➕ Add comparison panel",            "➕ Añadir panel de comparación"),
    "explorer_remove_panel":     ("Remove this panel",                 "Eliminar este panel"),
    "explorer_panel_label":      ("**Panel {label}**",                 "**Panel {label}**"),
    "explorer_filter_title":     ("🔎 Filter paths",                    "🔎 Filtrar trayectorias"),
    "explorer_outcome_label":    ("Outcome",                           "Resultado"),
    "explorer_outcome_any":      ("Any",                               "Cualquiera"),
    "explorer_outcome_autocalled": ("Autocalled",                      "Autocancelada"),
    "explorer_outcome_maturity": ("Held to maturity",                  "Hasta vencimiento"),
    "explorer_outcome_loss":     ("Capital loss",                      "Pérdida de capital"),
    "explorer_ac_period_label":  ("Autocall period (blank = any)",     "Período de autocancelación (vacío = cualquiera)"),
    "explorer_ki_label":         ("Knock-in",                          "Knock-in"),
    "explorer_ki_any":           ("Any",                               "Cualquiera"),
    "explorer_ki_yes":           ("Yes",                               "Sí"),
    "explorer_ki_no":            ("No",                                "No"),
    "explorer_return_label":     ("Total return range",                "Rango de retorno total"),
    "explorer_irr_label":        ("IRR range",                         "Rango de TIR"),
    "explorer_coupon_label":     ("Coupon paid at period(s)",          "Cupón pagado en período(s)"),
    "explorer_coupon_help":      ("Path must have paid a coupon at every selected period.",
                                  "La trayectoria debe haber pagado un cupón en cada período seleccionado."),
    "explorer_coupon_unavailable": ("Re-run the simulation to filter by coupon period.",
                                    "Vuelve a ejecutar la simulación para filtrar por período de cupón."),
    "explorer_match_count":      ("{m} of {total} paths match",        "{m} de {total} trayectorias coinciden"),
    "explorer_no_matches":       ("No paths match these filters — loosen them.",
                                  "Ninguna trayectoria coincide — relaja los filtros."),
    "explorer_match_caption":    ("Match {k} of {m} · path #{n}",      "Coincidencia {k} de {m} · trayectoria #{n}"),
    "explorer_bt_match_caption": ("Match {k} of {m} · issued {d}",     "Coincidencia {k} de {m} · emitida {d}"),
    "autocalled_at_md":          ("### Autocalled at period {q} ({t:.3g}Y)",
                                  "### Autocall en período {q} ({t:.3g}A)"),
    "maturity_knock_in_md":      ("### Maturity — Capital loss (worst-of: {wof:.1%})",
                                  "### Vencimiento — Pérdida de capital (worst-of: {wof:.1%})"),
    "maturity_no_knock_in_md": ("### Maturity — No capital loss (worst-of: {wof:.1%})",
                                  "### Vencimiento — Sin pérdida de capital (worst-of: {wof:.1%})"),
    "metric_principal":          ("Principal",                         "Principal"),
    "metric_coupons":            ("Coupons",                           "Cupones"),
    "metric_irr_pa":             ("IRR p.a.",                          "TIR p.a."),

    # ── MC tab4 — correlation ──────────────────────────────────────────────
    "corr_diag_subheader":       ("Correlation Diagnostics",           "Diagnóstico de Correlaciones"),
    "calib_heston_subheader":    ("Calibrated Heston Parameters",      "Parámetros Heston Calibrados"),
    "t_copula_dof":              ("**Student-t Copula:** ν = {v} d.f.", "**Cópula Student-t:** ν = {v} g.l."),

    # ── Backtest tab — headers and intros ──────────────────────────────────
    "bt_tab_header":             ("Historical Backtest",            "Backtest Histórico"),
    "bt_tab_intro":              (
        "Evaluates this note on every valid issue date using actual realized prices.",
        "Evalúa esta nota en cada fecha de emisión válida usando precios reales realizados.",
    ),
    "bt_valid_dates_caption":    (
        "Valid issue dates: **{start} → {end}** "
        "(issues run from the start of aligned history — e.g. the latest IPO — up to"
        "{mat:g}Y before the end of data, so each issue has a full realized"
        "price path; aligned history: {hist_start} → {hist_end}).",
        "Fechas de emisión válidas: **{start} → {end}** "
        "(emisiones desde el inicio del historial alineado — ej. la última OPV — hasta"
        "{mat:g}A antes del fin de los datos, para que cada emisión tenga un path completo; "
        "historial alineado: {hist_start} → {hist_end}).",
    ),
    "bt_start_label":            ("Backtest start (issue dates from)", "Inicio del backtest (fechas de emisión desde)"),
    "bt_end_label":              ("Backtest end (issue dates until)",   "Fin del backtest (fechas de emisión hasta)"),
    "bt_apply_btn":              ("Apply",                             "Aplicar"),
    "bt_date_order_warning":     ("Backtest start is after end — range not applied.",
                                  "El inicio del backtest es posterior al fin — rango no aplicado."),
    "bt_metric_issue_dates":     ("Issue Dates",                       "Fechas de Emisión"),
    "bt_metric_mean_irr":        ("Mean IRR",                          "TIR Promedio"),
    "bt_metric_median_irr":      ("Median IRR",                        "TIR Mediana"),
    "bt_metric_total_return":    ("Total Return",                      "Retorno Total"),
    "bt_metric_coupon":          ("Coupon Income",                     "Cupón"),
    "bt_returns_label":          ("Realised return",                   "Retorno realizado"),
    "bt_sample_caption":         ("Backtested across {n} historical issue dates.",
                                  "Backtest sobre {n} fechas de emisión históricas."),
    "bt_median_caption":         ("median IRR {v}",                    "TIR mediana {v}"),
    "bt_metric_knock_in_pct":    ("Knock-in %",                        "% Knock-in"),
    "bt_metric_autocalled_pct":  ("Autocalled %",                      "% Autocall"),
    "bt_path_explorer_header": ("Historical Path Explorer",       "Explorador de Trayectorias Históricas"),
    "bt_path_explorer_caption":  (
        "Select any issue date from the backtest to see the actual"
        "per-asset performance and worst-of path over the note's life.",
        "Selecciona cualquier fecha de emisión del backtest para ver el rendimiento real"
        "por activo y la trayectoria worst-of durante la vida de la nota.",
    ),
    "bt_issue_date_select":      ("Issue date",                        "Fecha de emisión"),
    "bt_outcome_label":          ("**Outcome:** {outcome}",            "**Resultado:** {outcome}"),
    "bt_irr_label":              ("**IRR:** {irr:.2%}",                "**TIR:** {irr:.2%}"),
    "bt_worst_asset_label":      ("**Worst asset:** {asset} ({perf:.1%})",
                                  "**Activo más débil:** {asset} ({perf:.1%})"),

    # ── Backtest outcome values (bt['Outcome']) ────────────────────────────
    "bt_outcome_maturity":       ("Maturity",                          "Vencimiento"),
    "bt_outcome_knock_in":       ("Knock-in",                          "Knock-in"),
    "bt_outcome_autocalled_p":   ("Autocalled P{i}",                   "Autocancelada P{i}"),
    "bt_not_enough_history":     (
        "**Not enough history for this note.** A {mat:g}Y note needs "
        "one full {mat:g}-year calendar window of realized prices after "
        "the first issue date, but the aligned history across all underlyings only "
        "spans {start} → {end}.",
        "**Historial insuficiente para esta nota.** Una nota de {mat:g}A necesita "
        "una ventana calendario completa de {mat:g} años de precios reales tras "
        "la primera fecha de emisión, pero el historial alineado entre todos los "
        "subyacentes solo abarca {start} → {end}.",
    ),
    "bt_no_price_history":       ("Could not load price history for the backtest.",
                                  "No se pudo cargar el historial de precios para el backtest."),
    "bt_failed":                 ("Backtest failed: {e}",              "El backtest falló: {e}"),
    "bt_no_results":             ("No backtest results. Check underlyings have sufficient history.",
                                  "Sin resultados de backtest. Verifique que los subyacentes tengan historial suficiente."),
    "bt_running":                ("Running historical backtest…",      "Ejecutando backtest histórico…"),
    "bt_could_not_build_path":   ("Could not build path: {e}",         "No se pudo construir la trayectoria: {e}"),
    "bt_help_issue_dates":       (
        "Number of distinct historical issue dates tested. Each date seeds "
        "an independent note life using the actual realized price path of "
        "the underlyings. The backtest slides a window of length = maturity "
        "across the full price history, one issue date per trading day.",
        "Número de fechas de emisión históricas distintas evaluadas. Cada fecha genera "
        "una vida de nota independiente usando la trayectoria real de precios de los "
        "subyacentes. El backtest desliza una ventana de longitud = vencimiento sobre "
        "todo el historial de precios, una fecha de emisión por día de negociación.",
    ),
    "bt_help_mean_irr":          (
        "Average of per-issue simple annualised returns: "
        "mean((payout − 1) ÷ holding time). Simple annualisation — not "
        "compound. Skewed upward by early autocalls that divide coupon "
        "income by a short holding period.",
        "Promedio de los rendimientos simples anualizados por emisión: "
        "media((pago − 1) ÷ tiempo de tenencia). Anualización simple — no "
        "compuesta. Sesgada al alza por autocancelaciones tempranas que dividen "
        "el ingreso por cupón entre un período de tenencia corto.",
    ),
    "bt_help_median_irr":        (
        "Median simple annualised return across all historical issue dates. "
        "Less sensitive than the mean to the skew introduced by very early "
        "autocalls; a better central-tendency estimate for most note structures.",
        "Rendimiento simple anualizado mediano entre todas las fechas de emisión "
        "históricas. Menos sensible que la media al sesgo introducido por "
        "autocancelaciones muy tempranas; una mejor estimación de tendencia central "
        "para la mayoría de las estructuras.",
    ),
    "bt_help_total_return":      (
        "Average total return at redemption across all historical issue dates: "
        "mean(payout − 1), i.e. coupons plus principal repayment over par. NOT "
        "annualised — over the realised holding period of each note.",
        "Retorno total medio al rescate entre todas las fechas de emisión históricas: "
        "media(pago − 1), es decir cupones más devolución de principal sobre la par. "
        "NO anualizado — sobre el período de tenencia real de cada nota.",
    ),
    "bt_help_coupon":            (
        "Average coupon income collected per note across all historical issue "
        "dates, as a fraction of par. Early autocalls collect fewer coupons.",
        "Ingreso medio por cupones cobrado por nota entre todas las fechas de emisión "
        "históricas, como fracción de la par. Las autocancelaciones tempranas cobran "
        "menos cupones.",
    ),
    "bt_help_knock_in_pct":      (
        "Fraction of historical issue dates where the knock-in barrier was "
        "breached AND the final redemption condition was not met, resulting "
        "in a capital loss. Notes with a best-of rescue clause show a lower "
        "figure here than the raw barrier-breach rate.",
        "Fracción de fechas de emisión históricas donde la barrera de knock-in fue "
        "tocada Y la condición de redención final no se cumplió, resultando en una "
        "pérdida de capital. Las notas con cláusula de rescate best-of muestran una "
        "cifra menor aquí que la tasa bruta de ruptura de barrera.",
    ),
    "bt_help_autocalled_pct":    (
        "Fraction of historical issue dates where the note was called early "
        "at an autocall observation date before maturity.",
        "Fracción de fechas de emisión históricas donde la nota fue cancelada "
        "anticipadamente en una fecha de observación antes del vencimiento.",
    ),
    "bt_help_loss_given_ki":     (
        "Mean realised annualised IRR on historical issue dates where the knock-in "
        "barrier was breached at maturity. Shows '—' if no knock-in events occurred "
        "in the backtest window.",
        "TIR anualizada media realizada en fechas de emisión históricas donde la "
        "barrera de knock-in fue tocada al vencimiento. Muestra '—' si no hubo "
        "eventos de knock-in en la ventana del backtest.",
    ),

    # ── Current Performance tab ────────────────────────────────────────────
    "live_tab_header_md":        (
        "**Issue date:** {issue} &nbsp;·&nbsp; "
        "**Maturity:** {mat} &nbsp;·&nbsp; "
        "**Elapsed:** {elapsed:.2f}Y &nbsp;·&nbsp; "
        "**Remaining:** {remaining:.2f}Y",
        "**Fecha de emisión:** {issue} &nbsp;·&nbsp; "
        "**Vencimiento:** {mat} &nbsp;·&nbsp; "
        "**Transcurrido:** {elapsed:.2f}A &nbsp;·&nbsp; "
        "**Restante:** {remaining:.2f}A",
    ),
    "live_metric_wof_today":     ("Worst-of Today",          "Worst-of Hoy"),
    "live_metric_vs_strike":     ("{v:.1%} vs strike",                 "{v:.1%} vs strike"),
    "live_group_today":          ("Today",                             "Hoy"),
    "live_group_barriers":       ("Barriers",                          "Barreras"),
    "live_metric_worst_asset":   ("Worst Asset",                       "Activo Más Débil"),
    "live_metric_vs_ki":         ("vs KI Barrier",                     "vs Barrera KI"),
    "live_metric_vs_autocall":   ("vs Autocall",                       "vs Autocall"),
    "live_metric_ki_buffer":     ("KI Buffer",                         "Margen vs KI"),
    "live_metric_ac_buffer":     ("Autocall Buffer",                   "Margen vs Autocall"),
    "live_delta_barrier_ref":    ("KI barrier: {barrier:.0%}",         "Barrera KI: {barrier:.0%}"),
    "live_delta_autocall_ref":   ("Autocall barrier: {barrier:.0%}",   "Barrera autocall: {barrier:.0%}"),
    "live_asset_perf_header":    ("#### Current Asset Performance",    "#### Rendimiento Actual por Activo"),
    "live_obs_history_header":   ("#### Observation History",          "#### Historial de Observaciones"),
    "live_col_period":           ("Period",                            "Período"),
    "live_col_date":             ("Date",                              "Fecha"),
    "live_col_status":           ("Status",                            "Estado"),
    "live_col_wof":              ("Worst-of",                "Worst-of"),
    "live_col_coupon":           ("Coupon",                            "Cupón"),
    "live_col_cumulative":       ("Cumulative",                        "Acumulado"),
    "live_pending_coupons_info": (
        "**{n} coupon(s) pending** in memory — "
        "worth **{val:.4%}** "
        "(paid when worst-of next exceeds {barrier:.0%}).",
        "**{n} cupón/es pendiente(s)** en memoria — "
        "equivalen a **{val:.4%}** "
        "(se pagan cuando el worst-of supere {barrier:.0%}).",
    ),
    "live_coupon_irr_metric":    ("Coupon IRR to date (annualised)",   "TIR de cupones hasta hoy (anualizada)"),

    # ── Backtest ───────────────────────────────────────────────────────────
    "outcome_dist":             ("Outcome Distribution",            "Distribución de Resultados"),
    "count":                    ("Count",                           "Cantidad"),
    "worst_asset_at_mat":       ("Worst-of Asset at Maturity (uncalled notes)",
                                 "Activo Worst-of al Vencimiento (notas no rescatadas)"),
    "realised_irr_title":       ("Realised IRR by Issue Date",      "TIR Realizada por Fecha de Emisión"),
    "break_even":               ("Break-even",                      "Break-even"),
    "backtest_start":           ("Backtest start",                  "Inicio backtest"),
    "backtest_end":             ("Backtest end",                    "Fin backtest"),
    "normalised_level":         ("Normalised Level (base=100)",     "Nivel Normalizado (base=100)"),
    "date_axis":                ("Date",                            "Fecha"),

    # ── Outcome labels (used in bt["Outcome"]) ─────────────────────────────
    "outcome_maturity":         ("Maturity",                        "Vencimiento"),

    # ── Misc ───────────────────────────────────────────────────────────────

    # ── Setup page ─────────────────────────────────────────────────────────
    "setup_title":              ("Structured Note Simulator",          "Simulador de Notas Estructuradas"),
    "setup_intro":              ("Configure the note below, then click **Confirm & Run** to load the dashboard.",
                                 "Configure la nota a continuación, luego haga clic en **Confirmar y Ejecutar** para cargar el panel."),
    "setup_upload_label":       ("Upload note config (JSON) — optional",
                                 "Cargar configuración de la nota (JSON) — opcional"),
    "setup_invalid_json":       ("Invalid JSON: {e}",                  "JSON inválido: {e}"),
    "setup_config_loaded":      ("Config loaded: **{name}**",          "Configuración cargada: **{name}**"),
    "setup_underlyings_header": ("Underlyings",                        "Subyacentes"),
    "setup_select_underlyings": ("Select underlyings (1–5)",           "Seleccione subyacentes (1–5)"),
    "setup_add_custom_expander":("Add a custom ticker (not in the list above)",
                                 "Agregar un ticker personalizado (que no esté en la lista anterior)"),
    "setup_custom_caption":     ("Enter any valid yfinance symbol, e.g. UBER, 2222.SR, BTC-USD",
                                 "Ingrese cualquier símbolo válido de yfinance, ej. UBER, 2222.SR, BTC-USD"),
    "setup_custom_logos_header": ("Custom underlying logos (optional)",
                                  "Logos personalizados de subyacentes (opcional)"),
    "setup_custom_logos_caption":(
        "Upload your own logo for any underlying to override the automatic "
        "favicon/CDN logo — used in the app and the PDF report.",
        "Suba su propio logo para cualquier subyacente y reemplace el logo "
        "automático (favicon/CDN) — se usa en la app y en el informe PDF.",
    ),
    "setup_custom_logo_clear":  ("Reset",                              "Restablecer"),
    "setup_custom_symbol":      ("yfinance symbol",                    "Símbolo yfinance"),
    "setup_display_name":       ("Display name",                       "Nombre"),
    "setup_add_btn":            ("Add",                                "Agregar"),
    "setup_enter_both":         ("Enter both a symbol and a display name.",
                                 "Ingrese tanto un símbolo como un nombre."),
    "setup_note_terms":         ("Note Terms",                         "Términos de la Nota"),
    "setup_note_name":          ("Note name",                          "Nombre de la nota"),
    "setup_note_name_help":     ("Display name used in the dashboard and PDF report.",
                                 "Nombre usado en el panel y en el informe PDF."),
    "setup_maturity_years":     ("Maturity (years)",                   "Vencimiento (años)"),
    "setup_payment_freq":       ("Payment frequency",                  "Frecuencia de pago"),
    "setup_obs_periods_caption":("→ **{n} observation periods** ({per_yr}×/yr × {mat}Y)",
                                 "→ **{n} períodos de observación** ({per_yr}×/año × {mat}A)"),
    "setup_autocall_start":     ("Autocall start period",              "Período de inicio de autocall"),
    "setup_autocall_start_help":("First N periods are coupon-only (no autocall trigger).",
                                 "Los primeros N períodos son solo de cupón (sin disparador de autocall)."),
    "setup_coupon_pa":          ("Coupon p.a. (%)",                    "Cupón anual (%)"),
    "setup_coupon_pa_help":     ("Annualised coupon rate. Per-period rate is derived automatically.",
                                 "Tasa de cupón anualizada. La tasa por período se deriva automáticamente."),
    "setup_coupon_period_caption":("→ **{v:.4f}% per period**",        "→ **{v:.4f}% por período**"),
    "setup_coupon_barrier":     ("Coupon barrier (%)",                 "Barrera de cupón (%)"),
    "setup_memory_coupon":      ("Memory coupon",                      "Cupón con memoria"),
    "setup_autocall_barrier":   ("Autocall barrier (%)",               "Barrera de autocall (%)"),
    "setup_ki_barrier":         ("Knock-in barrier (%)",               "Barrera de knock-in (%)"),
    "setup_basket_types":       ("Performance Rule",                       "Regla de Rendimiento"),
    "setup_coupon_check":       ("Coupon barrier check",               "Comprobación de barrera de cupón"),
    "setup_autocall_check":     ("Autocall trigger check",             "Comprobación del disparador de autocall"),
    "setup_one_star_toggle":    ("One Star feature",                   "Función One Star"),
    "setup_one_star_help":      (
        "If ON: a single underlying at or above the One Star level satisfies the "
        "coupon, autocall AND final-redemption conditions on its own — capital is "
        "returned at par even when the knock-in is breached (BNP-style 'One Star', "
        "also covers the BBVA 'Barrier and Knock-in' rescue). If OFF: standard "
        "worst-of behaviour throughout.",
        "Si está activado: un único subyacente en o por encima del nivel One Star "
        "satisface por sí solo las condiciones de cupón, autocall y redención final "
        "— el capital se devuelve a la par incluso si se toca el knock-in (tipo BNP "
        "'One Star', también cubre el rescate 'Barrier and Knock-in' de BBVA). Si "
        "está desactivado: comportamiento worst-of estándar.",
    ),
    "setup_one_star_level":     ("One Star level (% of initial)",      "Nivel One Star (% del inicial)"),
    "setup_one_star_level_help":(
        "Any single underlying at or above this level triggers the coupon, autocall "
        "and par redemption. Term sheets typically use 100%.",
        "Cualquier subyacente en o por encima de este nivel dispara el cupón, el "
        "autocall y la redención a la par. Los term sheets suelen usar 100%.",
    ),
    "setup_advanced_expander":  ("Advanced — Growth / Classic Autocall (step-down barrier, premium at call)",
                                 "Avanzado — Autocall Growth / Clásico (barrera escalonada, prima al rescate)"),
    "setup_step_down":          ("Autocall step-down per period (%)",   "Reducción de autocall por período (%)"),
    "setup_step_down_help":     (
        "The autocall barrier declines by this amount each period "
        "from the first callable observation. 0 = constant barrier "
        "(plain Phoenix).",
        "La barrera de autocall disminuye en esta cantidad cada período desde la "
        "primera observación rescatable. 0 = barrera constante (Phoenix estándar).",
    ),
    "setup_autocall_floor":     ("Autocall barrier floor (%)",         "Piso de la barrera de autocall (%)"),
    "setup_autocall_floor_help":(
        "Minimum barrier level under step-down. 0 = no floor. "
        "Ignored when step-down is 0.",
        "Nivel mínimo de barrera bajo la reducción escalonada. 0 = sin piso. "
        "Se ignora cuando la reducción es 0.",
    ),
    "setup_premium_at_call":    ("Premium only at autocall",           "Prima solo al autocall"),
    "setup_premium_at_call_help":(
        "Growth autocall: no periodic coupon — an accrued premium of "
        "coupon p.a. × elapsed periods is paid as a lump only when "
        "the note autocalls (zero if held to maturity). "
        "E.g. Citi XS3096699163.",
        "Autocall growth: sin cupón periódico — una prima acumulada de cupón anual × "
        "períodos transcurridos se paga de una vez solo cuando la nota se autocancela "
        "(cero si se mantiene hasta el vencimiento). Ej. Citi XS3096699163.",
    ),
    "setup_barrier_schedule":   ("Barrier schedule: ",                 "Calendario de barreras: "),
    "setup_issuer_header":      ("Issuer (optional)",                  "Emisor (opcional)"),
    "setup_issuer_caption":     ("Name of the bank or institution that issued this note — used for display only.",
                                 "Nombre del banco o institución que emitió esta nota — solo para visualización."),
    "setup_issuer_name":        ("Issuer name",                        "Nombre del emisor"),
    "setup_issuer_description": ("Issuer description",                 "Descripción del emisor"),
    "setup_issuer_description_help": (
        "Short profile of the issuing institution. Shown in the PDF's "
        "'Issuer Information' section (on by default).",
        "Perfil breve de la institución emisora. Se muestra en la sección "
        "'Información del Emisor' del PDF (activada por defecto).",
    ),
    "setup_rating_sp":          ("S&P rating",                         "Calificación S&P"),
    "setup_rating_moody":       ("Moody's rating",                     "Calificación Moody's"),
    "setup_rating_fitch":       ("Fitch rating",                       "Calificación Fitch"),
    "setup_issuer_logo":        ("Issuer logo (optional)",             "Logo del emisor (opcional)"),
    "setup_issuer_logo_help":   (
        "Upload a custom issuer logo (PNG/JPG). Overrides the auto-fetched "
        "favicon — use this when the favicon can't be found.",
        "Suba un logo personalizado del emisor (PNG/JPG). Reemplaza el favicon "
        "obtenido automáticamente — útil cuando el favicon no se encuentra.",
    ),
    "setup_issuer_logo_clear":  ("Clear logo",                         "Quitar logo"),
    "setup_issue_date_header":  ("Issue Date (optional)",              "Fecha de Emisión (opcional)"),
    "setup_issue_date_caption": ("If set to today or earlier, a **Current Performance** tab will appear on the dashboard.",
                                 "Si se fija en la fecha de hoy o anterior, aparecerá una pestaña de **Rendimiento Actual** en el panel."),
    "setup_issue_date_input":   ("Note issue date (leave blank for hypothetical notes)",
                                 "Fecha de emisión de la nota (deje en blanco para notas hipotéticas)"),
    "setup_issue_date_help":    ("Populated automatically from JSON config. Set to a past or current date to enable live tracking.",
                                 "Se completa automáticamente desde la configuración JSON. Fije una fecha pasada o actual para habilitar el seguimiento en vivo."),
    "setup_live_note":          ("Live note · issued {date} · **Current Performance** tab will appear on the dashboard.",
                                 "Nota en vivo · emitida el {date} · la pestaña de **Rendimiento Actual** aparecerá en el panel."),
    "setup_future_issue":       ("Issue date is in the future — Current Performance tab will appear once trading begins.",
                                 "La fecha de emisión es futura — la pestaña de Rendimiento Actual aparecerá cuando comience la negociación."),
    "setup_simulation_header":  ("Simulation",                         "Simulación"),
    "setup_mc_paths":           ("Monte Carlo paths",                  "Trayectorias de Monte Carlo"),
    "setup_random_seed":        ("Random seed",                        "Semilla aleatoria"),
    "setup_historical_data":    ("Historical Data",                    "Datos Históricos"),
    "setup_price_history_caption":(
        "Price history: **Max (all available)** — aligned across underlyings, "
        "so the common start is set by the shortest-history asset (e.g. latest IPO).",
        "Historial de precios: **Máximo (todo lo disponible)** — alineado entre "
        "subyacentes, por lo que el inicio común lo define el activo de historial más "
        "corto (ej. la OPV más reciente).",
    ),
    "setup_calib_window":       ("Calibration window (Heston params estimated on this recent period only)",
                                 "Ventana de calibración (los parámetros Heston se estiman solo en este período reciente)"),
    "setup_calib_window_help":  (
        "Keep short (2–5Y) for forward-looking drift and vol. "
        "Longer windows drag mu negative when they include major crashes (e.g. 2008 for bank stocks).",
        "Mantenga corta (2–5A) para un drift y volatilidad prospectivos. Ventanas más "
        "largas arrastran mu hacia negativo cuando incluyen grandes caídas (ej. 2008 para bancos).",
    ),
    "setup_calib_1y":           ("1 Year",                             "1 Año"),
    "setup_calib_2y":           ("2 Years",                            "2 Años"),
    "setup_calib_3y":           ("3 Years",                            "3 Años"),
    "setup_calib_5y":           ("5 Years",                            "5 Años"),
    "setup_calib_10y":          ("10 Years",                           "10 Años"),
    "setup_select_min_one":     ("Select at least 1 underlying to continue.",
                                 "Seleccione al menos 1 subyacente para continuar."),
    "setup_confirm_btn":        ("Confirm & Load Dashboard",           "Confirmar y Cargar Panel"),

    # ── Note-type template picker ──────────────────────────────────────────
    "setup_note_type_header":   ("Note type",                          "Tipo de nota"),
    "setup_note_type":          ("What kind of note is this?",         "¿Qué tipo de nota es?"),
    "setup_note_type_help":     ("Pick a template to show only the fields this structure needs.",
                                 "Elija una plantilla para mostrar solo los campos que esta estructura necesita."),
    "nt_phoenix":               ("Phoenix",                            "Phoenix"),
    "nt_reverse_conv":          ("Reverse Convertible",                "Reverse Convertible"),
    "nt_growth_autocall":       ("Growth Autocall",                    "Autocall creciente"),
    "nt_bonus_cert":            ("Bonus Certificate",                  "Certificado Bonus"),
    "nt_capital_protected":     ("Capital-Protected",                  "Capital protegido"),
    "nt_custom":                ("Custom",                             "Personalizado"),
    "nt_phoenix_desc":          ("Periodic coupon when performance is above the coupon barrier; redeems early above the autocall barrier; capital at risk below the knock-in.",
                                 "Cupón periódico cuando el rendimiento está sobre la barrera de cupón; rescate anticipado sobre la barrera de autocall; capital en riesgo bajo el knock-in."),
    "nt_reverse_conv_desc":     ("Guaranteed coupon every period (no coupon barrier); capital at risk below the knock-in at maturity.",
                                 "Cupón garantizado cada período (sin barrera de cupón); capital en riesgo bajo el knock-in al vencimiento."),
    "nt_growth_autocall_desc":  ("No periodic coupon — an accrued premium is paid only if the note autocalls. The autocall barrier steps down each period.",
                                 "Sin cupón periódico — se paga una prima acumulada solo si la nota hace autocall. La barrera de autocall baja cada período."),
    "nt_bonus_cert_desc":       ("No coupons. At maturity pays the better of the underlying performance or a guaranteed floor, unless the knock-in was breached.",
                                 "Sin cupones. Al vencimiento paga lo mejor entre el rendimiento del subyacente o un piso garantizado, salvo que se haya tocado el knock-in."),
    "nt_capital_protected_desc":("No coupons. Redemption is the underlying performance clipped between a guaranteed capital floor and an upside cap.",
                                 "Sin cupones. El rescate es el rendimiento del subyacente acotado entre un piso de capital garantizado y un techo de subida."),
    "nt_custom_desc":           ("All fields exposed — build any Phoenix-family structure (step-down, One Star, guaranteed coupon, …).",
                                 "Todos los campos visibles — construya cualquier estructura de la familia Phoenix (step-down, rescate best-of, cupón garantizado, …)."),

    # ── Setup section headers (regrouped form) ─────────────────────────────
    "setup_schedule_header":    ("Schedule & Maturity",                "Calendario y Vencimiento"),
    "setup_coupon_header":      ("Coupon",                             "Cupón"),
    "setup_barriers_header":    ("Protection / Barriers",              "Protección / Barreras"),
    "setup_autocall_header":    ("Autocall",                           "Autocall"),
    "setup_growth_subheader":   ("Step-down (growth autocall)",        "Step-down (autocall creciente)"),
    "setup_metadata_header":    ("Metadata & identification (optional)","Metadatos e identificación (opcional)"),
    "setup_engine_header":      ("Simulation engine settings",         "Configuración del motor de simulación"),
    "setup_engine_select":      ("Compute engine",                     "Motor de cálculo"),
    "setup_engine_numpy":       ("NumPy (default)",                    "NumPy (predeterminado)"),
    "setup_engine_cpp":         ("C++ (multi-core)",                   "C++ (multinúcleo)"),
    "setup_engine_help":        ("NumPy is the reference engine (no build step). C++ is the compiled, "
                                 "multi-core engine — identical results, faster on multi-core machines. "
                                 "Build it with `pip install ./cpp`.",
                                 "NumPy es el motor de referencia (sin compilación). C++ es el motor compilado "
                                 "y multinúcleo — resultados idénticos, más rápido en máquinas multinúcleo. "
                                 "Compílalo con `pip install ./cpp`."),
    "setup_engine_cpp_unbuilt": ("⚠️ C++ engine not built — run `pip install ./cpp` to enable it. "
                                 "NumPy will be used until then.",
                                 "⚠️ Motor C++ no compilado — ejecuta `pip install ./cpp` para activarlo. "
                                 "Se usará NumPy mientras tanto."),
    "mc_engine_caption":        ("Engine: {engine} · {paths:,} paths · {secs:.2f}s",
                                 "Motor: {engine} · {paths:,} trayectorias · {secs:.2f}s"),
    "mc_cpp_fallback":          ("C++ engine unavailable ({e}); ran with NumPy instead.",
                                 "Motor C++ no disponible ({e}); se ejecutó con NumPy."),
    "setup_mem_estimate":       ("≈ {gb:.1f} GB peak memory for this run · {ram:.0f} GB on this machine.",
                                 "≈ {gb:.1f} GB de memoria pico para esta ejecución · {ram:.0f} GB en esta máquina."),
    "setup_mem_estimate_noram": ("≈ {gb:.1f} GB peak memory for this run (full daily paths are kept).",
                                 "≈ {gb:.1f} GB de memoria pico (se conservan todas las trayectorias diarias)."),
    "setup_mem_warn":           ("⚠️ ≈ {gb:.1f} GB peak for this path count — heavy on {ram:.0f} GB of RAM. The "
                                 "engine keeps every daily step for all paths, so it may swap to disk and stall. "
                                 "Lower the path count or shorten the note.",
                                 "⚠️ ≈ {gb:.1f} GB pico para esta cantidad de trayectorias — exigente con {ram:.0f} GB "
                                 "de RAM. El motor conserva cada paso diario de todas las trayectorias, así que puede "
                                 "usar disco (swap) y atascarse. Reduce las trayectorias o acorta la nota."),
    "mc_mem_block":             ("This run needs ≈ {gb:.1f} GB but the machine has only {ram:.0f} GB — it would swap "
                                 "to disk and hang (this is what made it stall before). Reduce Monte Carlo paths to "
                                 "about {safe:,} or fewer for this note, then run again.",
                                 "Esta ejecución necesita ≈ {gb:.1f} GB pero la máquina tiene solo {ram:.0f} GB — "
                                 "usaría disco (swap) y se colgaría (esto es lo que la atascó antes). Reduce las "
                                 "trayectorias de Monte Carlo a unas {safe:,} o menos para esta nota y vuelve a ejecutar."),
    "mc_status_title":          ("Running Monte Carlo…",                "Ejecutando Monte Carlo…"),
    "mc_status_loading":        ("Loading & aligning market data…",     "Cargando y alineando datos de mercado…"),
    "mc_status_calibrating":    ("Calibrating Heston parameters…",      "Calibrando parámetros de Heston…"),
    "mc_status_simulating":     ("Simulating {paths:,} paths · {engine}…",
                                 "Simulando {paths:,} trayectorias · {engine}…"),
    "mc_status_pricing":        ("Evaluating the note payoff…",         "Evaluando el pago de la nota…"),
    "mc_status_done":           ("Done in {secs:.1f}s",                 "Listo en {secs:.1f}s"),

    # ── Setup inline help / captions ───────────────────────────────────────
    "setup_barriers_caption":   ("All barriers are a % of each underlying's initial level (100% = starting price).",
                                 "Todas las barreras son un % del nivel inicial de cada subyacente (100% = precio de partida)."),
    "setup_coupon_barrier_help":("0% = the coupon always pays (guaranteed-coupon / Reverse Convertible).",
                                 "0% = el cupón siempre paga (cupón garantizado / Reverse Convertible)."),
    "setup_memory_help":        ("Missed coupons are stored and paid later if a future period recovers above the barrier.",
                                 "Los cupones no pagados se acumulan y se pagan si un período futuro recupera sobre la barrera."),
    "setup_basket_rule_help":   ("How multi-underlying performance is scored — worst-of uses the weakest performer.",
                                 "Cómo se evalúa el rendimiento de varios subyacentes — worst-of usa el más débil."),
    "setup_ki_european_caption":("Measured at maturity only (European knock-in).",
                                 "Se mide solo al vencimiento (knock-in europeo)."),

    # ── Setup renamed / new field labels ───────────────────────────────────
    "setup_coupon_basket_rule": ("Coupon rule",                 "Regla del cupón"),
    "setup_autocall_basket_rule":("Autocall rule",              "Regla del autocall"),
    "setup_premium_pa":         ("Premium p.a. (%)",                   "Prima anual (%)"),
    "setup_premium_pa_help":    ("Accrual rate of the premium paid at autocall (premium = this rate × periods elapsed).",
                                 "Tasa de acumulación de la prima pagada al autocall (prima = esta tasa × períodos transcurridos)."),
    "setup_min_return":         ("Minimum return floor (%)",           "Piso de retorno mínimo (%)"),
    "setup_min_return_help":    ("Guaranteed minimum payoff at maturity when the knock-in is not breached (Bonus Certificate).",
                                 "Pago mínimo garantizado al vencimiento si no se toca el knock-in (Certificado Bonus)."),
    "setup_capital_protected_toggle": ("Capital-protected note",        "Nota con capital protegido"),
    "setup_capital_protected_toggle_help":("Turn the note into a capital-protected structure: the engine ignores coupons, autocall and the knock-in, and redeems the worst-of performance clipped to the guarantee (and upside cap, if set).",
                                 "Convierte la nota en una estructura de capital protegido: el motor ignora cupones, autocall y el knock-in, y rescata el peor rendimiento acotado a la garantía (y al techo de subida, si se define)."),
    "setup_capital_guarantee":  ("Capital guarantee (% of par)",       "Garantía de capital (% del nominal)"),
    "setup_capital_guarantee_help":("Guaranteed minimum redemption (e.g. 100% or 95%). Activates the capital-protected payoff.",
                                 "Rescate mínimo garantizado (p. ej. 100% o 95%). Activa el pago de capital protegido."),
    "setup_cap_upside_toggle":  ("Cap the upside",                     "Limitar la subida"),
    "setup_upside_cap":         ("Upside cap (%)",                     "Techo de subida (%)"),
    "setup_upside_cap_help":    ("Maximum redemption above par. Leave unchecked for uncapped upside.",
                                 "Rescate máximo sobre el nominal. Desmarque para subida sin tope."),

    # ── Basket option labels ───────────────────────────────────────────────
    "basket_worst_of":          ("Worst-of",                 "Worst-of"),
    "basket_best_of":           ("Best-of",                            "Mejor rendimiento"),
    "basket_average":           ("Average",                            "Promedio"),

    # ── Frequency labels ───────────────────────────────────────────────────
    "freq_monthly":             ("Monthly",                            "Mensual"),
    "freq_quarterly":           ("Quarterly",                          "Trimestral"),
    "freq_semi_annual":         ("Semi-annual",                        "Semestral"),
    "freq_annual":              ("Annual",                             "Anual"),

    # ── Dashboard sidebar ──────────────────────────────────────────────────
    "sidebar_note":             ("Note",                               "Nota"),
    "sidebar_download_config":  ("Download config (JSON)",             "Descargar configuración (JSON)"),
    "sidebar_branding_label":   ("PDF branding (JSON) — optional",
                                 "Diseño del PDF (JSON) — opcional"),
    "sidebar_branding_help":    (
        "Optional firm branding for the generated PDF report ONLY — colors, logo and "
        "firm name. The web app theme is unaffected. Schema (all keys optional): "
        "{firm_name, primary_color, accent_color, chart_secondary_color, logo_file, "
        "logo_base64, logo_url, report_title, website, contact, footer_note}.",
        "Diseño corporativo opcional SOLO para el informe PDF generado — colores, logo y "
        "nombre de la firma. No afecta al tema de la aplicación web. Esquema (todas las "
        "claves opcionales): {firm_name, primary_color, accent_color, chart_secondary_color, "
        "logo_file, logo_base64, logo_url, report_title, website, contact, footer_note}.",
    ),
    "sidebar_branding_invalid": ("Branding JSON invalid: {e}",         "JSON de identidad inválido: {e}"),
    "sidebar_branding_caption": ("Branding: **{firm}** {color}",       "Identidad: **{firm}** {color}"),
    "sidebar_clear_branding":   ("Clear branding",                     "Quitar identidad"),
    "sidebar_generate_pdf":     ("Generate PDF Report",                "Generar Informe PDF"),
    "sidebar_generate_pdf_help":(
        "Builds the report, then a download button appears below. "
        "If no simulation has run yet, it runs one first.",
        "Construye el informe, luego aparece un botón de descarga abajo. "
        "Si aún no se ha ejecutado una simulación, ejecuta una primero.",
    ),
    "report_panel_header":      ("Build report — sections",            "Construir informe — secciones"),
    "report_panel_caption":     (
        "Everything is on by default. A category toggle selects/clears all of "
        "its items; untick anything you don't want. Sections with no data are "
        "skipped automatically.",
        "Todo está activado por defecto. Un interruptor de categoría "
        "selecciona/borra todos sus elementos; desmarque lo que no quiera. Las "
        "secciones sin datos se omiten automáticamente.",
    ),
    # Build-report categories (master toggles)
    "report_cat_note":          ("Note details",                       "Detalles de la nota"),
    "report_cat_mc":            ("Monte Carlo",                        "Monte Carlo"),
    "report_cat_bt":            ("Historical backtest",                "Backtest histórico"),
    "report_cat_live":          ("Current performance",                "Rendimiento actual"),
    # Build-report sub-items — Note details
    "rep_note_terms":           ("Note terms",                         "Términos de la nota"),
    "rep_note_obs":             ("Observation schedule",               "Calendario de observaciones"),
    "rep_note_issuer":          ("Issuer information",                 "Información del emisor"),
    "rep_note_uls":             ("Underlying breakdown",               "Análisis por subyacente"),
    # Build-report sub-items — Monte Carlo
    "rep_mc_summary":           ("Summary & metrics",                  "Resumen y métricas"),
    "rep_mc_autocall":          ("Autocall by period",                "Autocall por período"),
    "rep_mc_irr":               ("IRR distribution",                  "Distribución de TIR"),
    "rep_mc_wof":               ("Worst-of fan chart",                "Abanico worst-of"),
    "rep_mc_fans":              ("Per-underlying fans",               "Abanicos por subyacente"),
    "rep_mc_explorer":          ("Path explorer",                     "Explorador de trayectorias"),
    "rep_mc_corr":              ("Correlation diagnostics",           "Diagnóstico de correlaciones"),
    "rep_mc_calib":             ("Calibration table",                "Tabla de calibración"),
    # Build-report sub-items — Backtest
    "rep_bt_summary":           ("Summary & outcomes",               "Resumen y resultados"),
    "rep_bt_outcome":           ("Outcome distribution",             "Distribución de resultados"),
    "rep_bt_pie":               ("Worst-asset breakdown",            "Desglose de peor activo"),
    "rep_bt_irr":               ("IRR by issue date",               "TIR por fecha de emisión"),
    "rep_bt_prices":            ("Historical prices",               "Precios históricos"),
    "rep_bt_path":              ("Historical path explorer",        "Explorador de trayectorias históricas"),
    "rep_bt_explorer":          ("Path explorer",                   "Explorador de trayectorias"),
    # Build-report sub-items — Current performance
    "rep_live_metrics":         ("Summary metrics",                 "Métricas de resumen"),
    "rep_live_assets":          ("Per-asset table",                "Tabla por activo"),
    "rep_live_obs":             ("Observation history",            "Historial de observaciones"),
    "rep_live_chart":           ("Performance chart",              "Gráfico de rendimiento"),
    "sidebar_reconfigure":      ("Reconfigure Note",                   "Reconfigurar Nota"),
    "sidebar_download_pdf":     ("Download PDF",                       "Descargar PDF"),
    "building_pdf":             ("Building PDF report…",               "Construyendo informe PDF…"),

    # ── Dashboard header / structure ───────────────────────────────────────
    "dash_no_memory":           ("No memory",                          "Sin memoria"),
    "dash_memory":              ("Memory",                             "Memoria"),
    "structure_issuer_label":   ("Issuer:",                            "Emisor:"),
    "structure_group_schedule": ("Schedule",                           "Calendario"),
    "structure_group_coupon":   ("Coupon",                             "Cupón"),
    "structure_group_barriers": ("Barriers",                           "Barreras"),
    "autocall_eligible_yes":    ("Yes",                                "Sí"),
    "autocall_eligible_coupon_only":("Coupon only",                    "Solo cupón"),

    # ── MC tab — spinners / status ─────────────────────────────────────────
    "mc_run_spinner":           ("Running Heston calibration and Monte Carlo simulation…",
                                 "Ejecutando calibración Heston y simulación de Monte Carlo…"),
    "mc_div_warning":           ("Could not load dividend history ({e}) — simulating without dividend jumps.",
                                 "No se pudo cargar el historial de dividendos ({e}) — simulando sin saltos de dividendos."),
    "data_load_error":          ("**Could not load market data.** {msg}",
                                 "**No se pudieron cargar los datos de mercado.** {msg}"),
    "data_load_retry":          ("This is usually a transient Yahoo Finance rate-limit or network hiccup. "
                                 "Wait a moment and try again.",
                                 "Suele ser un límite de tasa o un problema de red transitorio de Yahoo Finance. "
                                 "Espere un momento e inténtelo de nuevo."),
    "mc_click_run_info":        ("Click **Run Simulation** in the sidebar to run the Monte Carlo engine.",
                                 "Haga clic en **Ejecutar Simulación** en la barra lateral para ejecutar el motor de Monte Carlo."),
    "mc_prefetch_spinner":      ("Pre-fetching market data for {tickers}…",
                                 "Obteniendo datos de mercado para {tickers}…"),
    "mc_market_ready":          ("Market data ready. Click **Run Simulation** in the sidebar.",
                                 "Datos de mercado listos. Haga clic en **Ejecutar Simulación** en la barra lateral."),
    "mc_fetch_failed":          ("Failed to fetch prices: {e}",        "Error al obtener precios: {e}"),

    # ── MC tab — tab names ─────────────────────────────────────────────────
    "tab_monte_carlo":          ("Monte Carlo",                        "Monte Carlo"),
    "tab_historical_backtest":  ("Historical Backtest",                "Backtest Histórico"),
    "tab_current_performance":  ("Current Performance",                "Rendimiento Actual"),

    # ── Tab intro bands — the three analysis lenses (future → past → present).
    # Each tab opens with the same band: a tense eyebrow + the question the lens
    # answers, so the three tabs read as one narrative arc.
    "tab_intro_mc_eyebrow":     ("Forward-looking · model-based",      "Prospectivo · basado en modelo"),
    "tab_intro_mc_q":           ("What could happen?",                 "¿Qué podría pasar?"),
    "tab_intro_bt_eyebrow":     ("Realised history",                   "Historia realizada"),
    "tab_intro_bt_q":           ("What would have happened?",          "¿Qué habría pasado?"),
    "tab_intro_live_eyebrow":   ("Live · today",                       "En vivo · hoy"),
    "tab_intro_live_q":         ("What is happening now?",             "¿Qué está pasando ahora?"),

    # ── MC summary metric tooltips ─────────────────────────────────────────
    "mc_help_expected_irr":     (
        "Average of per-path annualized returns: mean(return ÷ holding time). "
        "Early autocalls divide a small gain by a short holding period, so they "
        "contribute large positive IRRs; knock-in losses are spread over the full "
        "maturity. This can be positive even when Expected Total Return is "
        "negative (average of ratios ≠ ratio of averages), and implicitly assumes "
        "autocall proceeds are reinvested at similar rates.",
        "Promedio de los rendimientos anualizados por trayectoria: media(rendimiento ÷ "
        "tiempo de tenencia). Las autocancelaciones tempranas dividen una pequeña "
        "ganancia entre un período corto, contribuyendo con TIR altas y positivas; las "
        "pérdidas por knock-in se reparten sobre todo el vencimiento. Puede ser positiva "
        "incluso cuando el Rendimiento Total Esperado es negativo (media de cocientes ≠ "
        "cociente de medias), y asume implícitamente que el producto del autocall se "
        "reinvierte a tasas similares.",
    ),
    "mc_help_expected_return":  (
        "Average money outcome per 1.00 invested over the note's life: "
        "mean(payout − 1) = coupons received + principal returned − 1. "
        "Not annualized. The more conservative headline number.",
        "Resultado monetario promedio por cada 1.00 invertido durante la vida de la nota: "
        "media(pago − 1) = cupones recibidos + principal devuelto − 1. No anualizado. "
        "La cifra principal más conservadora.",
    ),
    "mc_help_expected_coupon":  (
        "Average total coupon income received over the note's life, per path "
        "(coupons across all periods, including memory catch-up payments). "
        "Expressed as a fraction of par. Does not include principal redemption.",
        "Ingreso total promedio por cupón recibido durante la vida de la nota, por "
        "trayectoria (cupones de todos los períodos, incluyendo pagos de memoria). "
        "Expresado como fracción del nominal. No incluye la redención del principal.",
    ),
    "mc_help_prob_autocall":    (
        "Probability the issuer exercises the call at any observation date "
        "before (or at) maturity. An autocall terminates the note early, "
        "returning principal plus the period coupon. Higher autocall barriers "
        "reduce this probability; the autocall start period locks out early "
        "observations from triggering.",
        "Probabilidad de que el emisor ejerza el call en cualquier fecha de observación "
        "antes del (o al) vencimiento. Una autocancelación termina la nota anticipadamente, "
        "devolviendo el principal más el cupón del período. Barreras de autocall más altas "
        "reducen esta probabilidad; el período de inicio del autocall bloquea las "
        "observaciones tempranas.",
    ),
    "mc_help_prob_knock_in":    (
        "Probability of a capital-costing knock-in at maturity: the worst-of "
        "finishes below the knock-in barrier AND the path is not rescued by the "
        "final (best-of) redemption clause. Rescued breaches redeem at par and "
        "are NOT counted. For worst-of notes (no rescue) this is just the "
        "barrier-breach rate.",
        "Probabilidad de un knock-in con pérdida de capital al vencimiento: el "
        "worst-of termina bajo la barrera de knock-in Y la trayectoria no es "
        "rescatada por la condición de redención final (best-of). Las trayectorias "
        "rescatadas redimen a la par y NO se cuentan. En notas worst-of (sin "
        "rescate) equivale a la tasa de toque de barrera.",
    ),
    "mc_help_loss_given_ki":     (
        "Mean annualised return (IRR) across the knock-in paths — those that "
        "breach the barrier at maturity and are not rescued. The average outcome "
        "when capital is actually lost. Shows '—' if no path knocks in.",
        "Retorno anualizado medio (TIR) en las trayectorias con knock-in — las que "
        "tocan la barrera al vencimiento y no son rescatadas. El resultado promedio "
        "cuando sí se pierde capital. Muestra '—' si ninguna hace knock-in.",
    ),
    "mc_help_principal":        (
        "Principal returned on this path as a fraction of par: 100% if "
        "the note autocalled or matured without a knock-in; the worst-of "
        "final performance if knock-in was triggered without a best-of "
        "rescue.",
        "Principal devuelto en esta trayectoria como fracción del nominal: 100% si la "
        "nota se autocanceló o venció sin knock-in; el rendimiento final worst-of si se "
        "activó el knock-in sin rescate best-of.",
    ),
    "mc_help_coupons":          (
        "Total coupon income received on this single path as a fraction "
        "of par, summing all paid periods (including memory catch-up "
        "payments if applicable).",
        "Ingreso total por cupón recibido en esta trayectoria como fracción del nominal, "
        "sumando todos los períodos pagados (incluyendo pagos de memoria si aplica).",
    ),
    "mc_help_irr_pa":           (
        "Simple annualised return for this single path: "
        "(principal + coupons − 1) ÷ holding time. "
        "Short autocall paths can show very high IRRs because the same "
        "coupon income is divided by a small holding period.",
        "Rendimiento simple anualizado para esta trayectoria: (principal + cupones − 1) "
        "÷ tiempo de tenencia. Las trayectorias con autocall corto pueden mostrar TIR muy "
        "altas porque el mismo ingreso por cupón se divide entre un período corto.",
    ),
    "mc_final_perf":            ("Final perf.",                        "Rend. final"),

    # ── Correlation heatmap labels + message ───────────────────────────────
    "corr_input":               ("Input",                              "Entrada"),
    "corr_realized":            ("Realized",                           "Realizada"),
    "corr_difference":          ("Difference",                         "Diferencia"),
    "corr_realized_caption":    (
        "**Realized** is the *instantaneous* correlation — each step's return is "
        "standardized by its own volatility before measuring, so it recovers the "
        "Brownian correlation that was actually fed into the simulation. This is "
        "the apples-to-apples check against the calibrated input.",
        "**Realizada** es la correlación *instantánea* — el retorno de cada paso se "
        "estandariza por su propia volatilidad antes de medir, recuperando la "
        "correlación browniana realmente usada en la simulación. Es la comparación "
        "directa contra la entrada calibrada.",
    ),
    "corr_quality_good":        ("good",                               "buena"),
    "corr_quality_acceptable":  ("acceptable",                         "aceptable"),
    "corr_quality_elevated":    ("elevated — consider more paths",     "elevada — considere más trayectorias"),
    "corr_max_err_message":     (
        "Max off-diagonal error: **{err:.4f}** ({quality}). "
        "Largest absolute gap between the calibrated input and the realized "
        "*instantaneous* correlation. Values < 0.05 confirm the engine reproduces "
        "the target correlation; if elevated, increase Monte Carlo paths.",
        "Error máximo fuera de la diagonal: **{err:.4f}** ({quality}). Mayor diferencia "
        "absoluta entre la entrada calibrada y la correlación *instantánea* realizada. "
        "Valores < 0.05 confirman que el motor reproduce la correlación objetivo; si es "
        "elevada, aumente las trayectorias de Monte Carlo.",
    ),
    "corr_effective_header":    ("Effective worst-of correlation (what the payoff sees)",
                                 "Correlación efectiva del worst-of (lo que ve el pago)"),
    "corr_effective":           ("Effective",                          "Efectiva"),
    "corr_effective_gap":       ("Gap vs input",                       "Brecha vs entrada"),
    "corr_effective_caption":   (
        "Correlation of pooled daily returns — the co-movement the worst-of actually "
        "experiences. It runs **above** the instantaneous input by construction: "
        "pooling high- and low-volatility days inflates sample correlation "
        "(heteroskedasticity / Forbes-Rigobon). This gap is expected, not a "
        "calibration error, and is largest for high vol-of-vol underlyings.",
        "Correlación de los retornos diarios agrupados — el co-movimiento que realmente "
        "experimenta el worst-of. Es **mayor** que la entrada instantánea por construcción: "
        "agrupar días de alta y baja volatilidad infla la correlación muestral "
        "(heterocedasticidad / Forbes-Rigobon). Esta brecha es esperada, no un error de "
        "calibración, y es mayor para subyacentes con alta volatilidad de la volatilidad.",
    ),
    "heston_feller_pass":       ("Pass",                               "Cumple"),
    "heston_feller_warn":       ("Warn",                               "Aviso"),
    "heston_col_feller":        ("Feller",                             "Feller"),
    "heston_column_guide":      (
        "**Column guide:** "
        "**μ** = arithmetic drift (annualised); "
        "**V₀ σ** = current implied vol (√V₀); "
        "**θ σ LR** = long-run vol mean (√θ, the level V reverts toward); "
        "**κ** = mean-reversion speed (higher → vol snaps back faster; typical equity: 1–5); "
        "**ξ** = vol-of-vol, volatility of the variance process (higher → fatter tails; typical: 0.1–0.8); "
        "**ρ** = leverage effect, correlation between spot and variance shocks "
        "(negative for equities — down moves spike vol; typical: −0.7 to −0.3); "
        "**Feller** = 'Pass' if 2κθ > ξ² (Feller condition), ensuring variance stays positive; "
        "'Warn' means variance can touch zero, which is a known Heston model artefact and "
        "generally has negligible pricing impact.",
        "**Guía de columnas:** "
        "**μ** = drift aritmético (anualizado); "
        "**V₀ σ** = volatilidad implícita actual (√V₀); "
        "**θ σ LR** = media de volatilidad de largo plazo (√θ, el nivel al que revierte V); "
        "**κ** = velocidad de reversión a la media (mayor → la vol regresa más rápido; "
        "renta variable típica: 1–5); "
        "**ξ** = vol-de-vol, volatilidad del proceso de varianza (mayor → colas más gruesas; "
        "típico: 0.1–0.8); "
        "**ρ** = efecto apalancamiento, correlación entre shocks de spot y varianza "
        "(negativo en renta variable — las caídas elevan la vol; típico: −0.7 a −0.3); "
        "**Feller** = 'Cumple' si 2κθ > ξ² (condición de Feller), garantizando que la "
        "varianza se mantenga positiva; 'Aviso' significa que la varianza puede tocar cero, "
        "un artefacto conocido del modelo Heston con impacto generalmente insignificante.",
    ),

    # ── MC path explorer buttons ───────────────────────────────────────────
    "btn_random":               ("Random",                             "Aleatoria"),
    "btn_prev":                 ("Prev",                               "Anterior"),
    "btn_next":                 ("Next",                               "Siguiente"),

    # ── Live tab — metric tooltips and statuses ────────────────────────────
    "live_help_wof_today":      (
        "Current level of the worst-performing underlying relative "
        "to its initial fixing price (strike = 100%). This is the "
        "key risk indicator: coupon and autocall eligibility, and "
        "knock-in exposure, are all measured against this figure.",
        "Nivel actual del subyacente de peor rendimiento relativo a su precio inicial de "
        "fijación (strike = 100%). Es el indicador clave de riesgo: la elegibilidad del "
        "cupón y del autocall, y la exposición al knock-in, se miden contra esta cifra.",
    ),
    "live_help_worst_asset":    (
        "The underlying currently dragging the worst-of — "
        "i.e. the one with the lowest performance relative to its "
        "initial fixing. This asset sets the barrier observation level.",
        "El subyacente que actualmente arrastra el worst-of — es decir, el de menor "
        "rendimiento relativo a su fijación inicial. Este activo determina el nivel de "
        "observación de la barrera.",
    ),
    "live_help_vs_ki":          (
        "Worst-of level as a percentage of the knock-in barrier "
        "({barrier:.0%}). "
        "Values > 100% mean the worst-of is above the KI barrier "
        "(no knock-in risk yet). The delta shows distance to the "
        "barrier in percentage-point terms.",
        "Nivel worst-of como porcentaje de la barrera de knock-in ({barrier:.0%}). "
        "Valores > 100% significan que el worst-of está por encima de la barrera de KI "
        "(sin riesgo de knock-in aún). El delta muestra la distancia a la barrera en "
        "puntos porcentuales.",
    ),
    "live_help_vs_autocall":    (
        "Worst-of level as a percentage of the autocall barrier "
        "({barrier:.0%}). "
        "Values ≥ 100% at an eligible observation date would "
        "trigger an early call. The delta shows distance to the "
        "barrier in percentage-point terms.",
        "Nivel worst-of como porcentaje de la barrera de autocall ({barrier:.0%}). "
        "Valores ≥ 100% en una fecha de observación elegible dispararían un rescate "
        "anticipado. El delta muestra la distancia a la barrera en puntos porcentuales.",
    ),
    "live_help_ki_buffer":      (
        "How far the worst-of is above the knock-in barrier ({barrier:.0%}), "
        "in percentage-point terms. Positive = safe; negative = barrier already breached. "
        "A breach at the final observation costs capital — unless a One Star "
        "clause (if this note has one) still returns par.",
        "Cuánto está el worst-of por encima de la barrera de knock-in ({barrier:.0%}), "
        "en puntos porcentuales. Positivo = seguro; negativo = barrera ya cruzada. "
        "Un cruce en la observación final cuesta capital — salvo que una cláusula de "
        "rescate best-of (si la nota la tiene) devuelva la par.",
    ),
    "live_help_ac_buffer":      (
        "How far the worst-of is above the autocall barrier ({barrier:.0%}), "
        "in percentage-point terms. Positive = the note could be called at the next "
        "eligible observation; negative = not yet at the call level.",
        "Cuánto está el worst-of por encima de la barrera de autocall ({barrier:.0%}), "
        "en puntos porcentuales. Positivo = la nota podría ser llamada en la próxima "
        "observación elegible; negativo = aún por debajo del nivel de llamada.",
    ),
    "live_help_coupon_irr":     (
        "Total coupons paid so far ÷ elapsed time in years — a simple "
        "(not compound) annualisation of income received. Does not "
        "include any accrued-but-unpaid memory coupons or the principal "
        "return at maturity. Comparable to a running yield on a bond, "
        "but note it overstates the realized return for notes where "
        "coupons cluster toward the end of the life.",
        "Total de cupones pagados hasta ahora ÷ tiempo transcurrido en años — una "
        "anualización simple (no compuesta) del ingreso recibido. No incluye cupones de "
        "memoria acumulados pero no pagados ni la devolución del principal al vencimiento. "
        "Comparable a un rendimiento corriente de un bono, pero sobreestima el rendimiento "
        "realizado en notas donde los cupones se concentran al final de la vida.",
    ),
    "live_history_warning":     (
        "Aligned price history only starts {anchor} — after the "
        "stated issue date {issue}. The initial fixing uses the "
        "first available close, so levels may not match the term sheet.",
        "El historial de precios alineado solo comienza el {anchor} — después de la fecha "
        "de emisión declarada {issue}. La fijación inicial usa el primer cierre disponible, "
        "por lo que los niveles pueden no coincidir con el term sheet.",
    ),
    "live_not_enough_data":     ("Not enough live price data since issue date.",
                                 "No hay suficientes datos de precios desde la fecha de emisión."),
    "live_status_upcoming":     ("Upcoming",                           "Próxima"),
    "live_status_autocalled":   ("Autocalled",                         "Autocancelada"),
    "live_status_no_coupon":    ("— No periodic coupon (premium at call)",
                                 "— Sin cupón periódico (prima al rescate)"),
    "live_status_coupon_paid":  ("Coupon paid",                        "Cupón pagado"),
    "live_status_coupon_missed":("Coupon missed",                      "Cupón no pagado"),
    "live_growth_premium_info": (
        "Growth autocall: no periodic coupons — an accrued premium of "
        "{rate:.2%} per period "
        "({pa:.0%} p.a.) is paid only if the note "
        "autocalls. Premium if called at the next eligible observation: "
        "{next_premium:.2%}.",
        "Autocall growth: sin cupones periódicos — una prima acumulada de {rate:.2%} por "
        "período ({pa:.0%} anual) se paga solo si la nota se autocancela. Prima si se "
        "rescata en la próxima observación elegible: {next_premium:.2%}.",
    ),
    "live_could_not_load":      ("Could not load live price data: {e}",
                                 "No se pudieron cargar los datos de precios en vivo: {e}"),
    "live_obs_dash":            ("—",                                  "—"),

    # ── Chart-internal strings (app/charts.py) ─────────────────────────────
    # Levels ({lvl}) and amounts ({v}, {pct}) are passed pre-formatted by the
    # caller so a single key serves both .0% and .1% precisions.
    "chart_worst_of":            ("Worst-of",                "Worst-of"),
    "chart_ki_barrier":          ("Knock-in barrier ({lvl})",          "Barrera knock-in ({lvl})"),
    "chart_autocall_barrier":    ("Autocall barrier",                  "Barrera autocall"),
    "chart_autocall_barrier_lvl":("Autocall barrier ({lvl})",          "Barrera autocall ({lvl})"),
    "chart_coupon_barrier_lvl":  ("Coupon barrier ({lvl})",            "Barrera de cupón ({lvl})"),
    "chart_perf_vs_issue":       ("Performance vs Issue Date",         "Rendimiento vs Fecha de Emisión"),
    "chart_today":               ("Today",                             "Hoy"),

    # IRR distribution (MC tab 1)
    "chart_irr_title":           ("Annualised IRR Distribution — All Simulated Paths",
                                  "Distribución de TIR Anualizada — Todas las Trayectorias Simuladas"),
    "chart_irr_xaxis":           ("Annualised IRR (simple)",           "TIR Anualizada (simple)"),
    "chart_irr_yaxis":           ("Share of all paths",                "Proporción de trayectorias"),
    "chart_irr_clip_note":       ("  ·  loss tail to {lvl} clipped into left bin",
                                  "  ·  cola de pérdidas hasta {lvl} recortada en la barra izquierda"),
    "chart_legend_autocalled":   ("Autocalled ({pct})",                "Rescatada ({pct})"),
    "chart_legend_maturity":     ("Maturity ({pct})",                  "Vencimiento ({pct})"),
    "chart_mean":                ("Mean {v}",                          "Media {v}"),
    "chart_coupon_pa":           ("Coupon {v} p.a.",                   "Cupón {v} anual"),
    # Discrete outcome breakdown — shown instead of the histogram when the IRR
    # distribution is near-degenerate (a near-certain single outcome). No chart
    # title: the app already shows an "IRR distribution" subheader above it.
    "chart_irr_bucket_autocall": ("Autocalled",                        "Rescatada"),
    "chart_irr_bucket_maturity": ("Held to maturity",                  "A vencimiento"),
    "chart_irr_bucket_loss":     ("Capital loss",                      "Pérdida de capital"),
    "chart_pa_suffix":           ("p.a.",                              "anual"),
    # Two-panel discrete breakdown: probability + mean return per outcome.
    "chart_disc_prob_panel":     ("Probability",                       "Probabilidad"),
    "chart_disc_return_panel":   ("Mean return by outcome",            "Retorno medio por escenario"),
    "chart_disc_total_return":   ("Total return",                      "Retorno total"),
    "chart_disc_irr_pa":         ("IRR p.a.",                          "TIR anual"),
    "chart_irr_flat_note":       ("Constant {v} p.a. across all {n} issue windows",
                                  "Constante {v} anual en las {n} ventanas de emisión"),

    # Backtest scatter/bar — px uses DataFrame column names as axis/legend
    # titles, so map them to translated display labels via labels=.
    "chart_issue_date_axis":     ("Issue Date",                        "Fecha de Emisión"),
    "chart_irr_axis":            ("IRR",                               "TIR"),
    "chart_outcome_axis":        ("Outcome",                           "Resultado"),
    "chart_payout_axis":         ("Payout",                            "Pago"),
    "chart_worst_asset_axis":    ("Worst Asset",                       "Activo Más Débil"),
    "chart_worst_final_perf_axis":("Worst Final Perf",                 "Rend. Final Worst-of"),

    # Backtest worst-asset pie, historical price + worst-of path charts
    "chart_worst_asset_at_call": ("Worst Asset at Call Date",          "Activo más débil en la fecha de rescate"),
    "chart_hist_prices_title":   ("Historical Price Paths",            "Trayectorias Históricas de Precio"),
    "chart_hist_wof_title":      ("Historical Worst-of Path — Issue: {issue} · Outcome: {outcome}",
                                  "Trayectoria Histórica Worst-of — Emisión: {issue} · Resultado: {outcome}"),
    "chart_outcome_autocalled_p":("Autocalled P{q}",                   "Rescatada P{q}"),
    "chart_period_called":       ("P{p} ← CALLED",                     "P{p} ← RESCATADA"),

    # Live performance chart
    "chart_live_title":          ("Live Performance — Issue: {issue} · Maturity: {mat}",
                                  "Rendimiento Actual — Emisión: {issue} · Vencimiento: {mat}"),
    "chart_marker_autocalled":   ("{label}: AUTOCALLED",               "{label}: RESCATADA"),
    "chart_marker_premium":      (" · Premium {v}",                    " · Prima {v}"),
    "chart_marker_coupon":       ("{label}: Coupon {v}",               "{label}: Cupón {v}"),
    "chart_marker_coupon_missed":("{label}: Coupon missed",            "{label}: Cupón no pagado"),
}


class Translator:
    """
    Callable translator.

    tr = Translator("en")
    tr("run_simulation")            # → "Run Simulation"
    tr("path_of", n=5, total=100)  # → "Path #5 of 100"  (supports .format kwargs)
    """

    def __init__(self, lang: str = "en") -> None:
        self.lang = lang.lower()

    def __call__(self, key: str, lang: str | None = None, **kwargs) -> str:
        effective = (lang or self.lang).lower()
        pair = _STRINGS.get(key)
        if pair is None:
            return key  # graceful fallback
        text = pair[1] if effective == "es"else pair[0]
        return text.format(**kwargs) if kwargs else text

    def set_lang(self, lang: str) -> None:
        self.lang = lang.lower()
