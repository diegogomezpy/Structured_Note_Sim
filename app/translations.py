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
    "note_parameters":          ("Note Parameters",                  "Parámetros de la Nota"),
    "coupon_label":             ("Coupon (% p.a.)",                  "Cupón (% anual)"),
    "coupon_help":              ("Annual coupon paid if the issuer calls the note early.",
                                 "Cupón anual pagado si el emisor rescata la nota anticipadamente."),
    "floor_label":              ("Capital Floor (%)",                "Piso de Capital (%)"),
    "floor_help":               ("Minimum redemption as % of notional at maturity.",
                                 "Redención mínima como % del nocional al vencimiento."),
    "sim_parameters":           ("Simulation Parameters",            "Parámetros de Simulación"),
    "mc_paths_label":           ("Monte Carlo Paths",                "Trayectorias de Monte Carlo"),
    "decisiveness_label":       ("Issuer Call Decisiveness",         "Decisión de Ejercicio del Emisor"),
    "decisiveness_help":        (
        "Controls how aggressively the issuer exercises the call. "
        "Low (~5): significant discretion around the strike. "
        "High (~50): nearly automatic when in-the-money.",
        "Controla qué tan agresivamente el emisor ejerce el call. "
        "Bajo (~5): discreción significativa cerca del strike. "
        "Alto (~50): casi automático cuando está in-the-money.",
    ),
    "seed_label":               ("Random Seed",                     "Semilla Aleatoria"),
    "run_simulation":           ("Run Simulation",               "Ejecutar Simulación"),

    # ── Page title / intro ─────────────────────────────────────────────────
    "page_title":               ("Multi-Asset Structured Note Simulator",
                                 "Simulador de Notas Estructuradas Multi-Activo"),
    "page_intro":               (
        "Historical Heston calibration + Monte Carlo simulation of a"
        "**worst-of callable note** on SPX / SX5E / SMI.",
        "Calibración histórica de Heston + simulación de Monte Carlo de una"
        "**callable note worst-of** sobre SPX / SX5E / SMI.",
    ),

    # ── Expander ───────────────────────────────────────────────────────────
    "how_note_works":           ("How This Note Works",           "Cómo Funciona Esta Nota"),
    "call_prob_curve":          ("#### Issuer Call Probability Curve",
                                 "#### Curva de Probabilidad de Ejercicio del Emisor"),
    "call_prob_caption":        (
        "Probability the issuer calls at a given worst-of performance level, "
        "for the current decisiveness setting.",
        "Probabilidad de que el emisor ejerza el call dado un nivel de rendimiento worst-of, "
        "con la configuración actual.",
    ),
    "worst_of_perf_axis":       ("Worst-of Performance",            "Rendimiento Worst-of"),
    "p_issuer_calls":           ("P(issuer calls)",                 "P(emisor ejerce)"),

    # ── Summary stats ──────────────────────────────────────────────────────
    "summary_statistics":       ("Summary Statistics",               "Resumen Estadístico"),
    "expected_irr":             ("Expected IRR",                     "TIR Esperada"),
    "expected_return":          ("Expected Return",                  "Rendimiento Esperado"),
    "prob_maturity":            ("Maturity Probability",             "Prob. de Vencimiento"),
    "prob_floor":               ("Capital Floor Probability",        "Prob. de Activación del Piso"),
    "issuer_call_probs":        ("Issuer Call Probabilities",        "Probabilidades de Ejercicio del Emisor"),
    "issuer_call_caption":      (
        "Probability the issuer exercises the call at each quarterly observation date.",
        "Probabilidad de que el emisor ejerza el call en cada fecha de observación trimestral.",
    ),
    "call_3m":                  ("3M Call",                          "Rescate 3M"),
    "call_6m":                  ("6M Call",                          "Rescate 6M"),
    "call_9m":                  ("9M Call",                          "Rescate 9M"),
    "reaches_maturity":         ("Reaches Maturity",                 "Llega al Vencimiento"),
    "sim_complete":             ("Simulation complete.",             "Simulación completada."),

    # ── Tab labels ─────────────────────────────────────────────────────────
    "tab_payoff":               ("Payoff & Distribution",         "Payoff y Distribución"),
    "tab_fan":                  ("Price Path Fan Chart",          "Abanico de Trayectorias de Precio"),
    "tab_explorer":             ("Path Explorer",                 "Explorador de Trayectorias"),
    "tab_corr":                 ("Correlation Diagnostics",       "Diagnóstico de Correlaciones"),

    # ── Tab 1 — Payoff ─────────────────────────────────────────────────────
    "payoff_subheader":         ("Maturity Payoff Profile vs Simulated Outcomes",
                                 "Perfil de Payoff al Vencimiento vs Resultados Simulados"),
    "payoff_caption":           (
        "The line shows the **contractual payoff** at maturity. "
        "The histogram shows the **distribution of simulated terminal worst-of values** "
        "for paths that reached maturity (not called early).",
        "La línea muestra el **payoff contractual** al vencimiento. "
        "El histograma muestra la **distribución de los valores terminales worst-of simulados** "
        "para las trayectorias que llegaron al vencimiento (no rescatadas anticipadamente).",
    ),
    "simulated_terminal":       ("Simulated terminal worst-of",      "Worst-of terminal simulado"),
    "contractual_payoff":       ("Contractual payoff",               "Payoff contractual"),
    "worst_of_final_perf":      ("Worst-of Final Performance",       "Rendimiento Final Worst-of"),
    "note_payoff":              ("Note Payoff",                      "Payoff de la Nota"),
    "prob_maturity_paths":      ("Probability (maturity paths)",     "Probabilidad (trayectorias al vencimiento)"),

    # ── Tab 2 — Fan ────────────────────────────────────────────────────────
    "fan_subheader":            ("Simulated Price Path Fan Chart",   "Abanico de Trayectorias de Precio Simuladas"),
    "fan_caption":              (
        "Percentile bands across all simulated paths. The **median** (50th) shows the"
        "central tendency; shaded bands show the spread.",
        "Bandas de percentiles sobre todas las trayectorias simuladas. La **mediana** (percentil 50) "
        "muestra la tendencia central; las bandas sombreadas muestran la dispersión.",
    ),
    "simulated_price_dist":     ("Simulated Price Distribution",     "Distribución de Precios Simulados"),
    "time_years":               ("Time (years)",                     "Tiempo (años)"),
    "price":                    ("Price",                            "Precio"),
    "median":                   ("Median",                           "Mediana"),
    "pct_5_95":                 ("5th–95th pct",                     "Pct 5–95"),
    "pct_25_75":                ("25th–75th pct",                    "Pct 25–75"),
    "wof_fan_subheader":        ("### Worst-of Performance Fan Chart","### Abanico de Rendimiento Worst-of"),
    "wof_fan_caption":          (
        "Percentile bands for the worst-of basket performance. "
        "The dashed line marks the 95% floor / call strike.",
        "Bandas de percentiles para el rendimiento de la cesta worst-of. "
        "La línea punteada marca el piso de capital / call strike del 95%.",
    ),
    "perf_vs_initial":          ("Performance vs Initial",           "Rendimiento vs Inicial"),

    # ── Tab 3 — Path Explorer ──────────────────────────────────────────────
    "explorer_subheader":       ("Single Path Explorer",             "Explorador de Trayectoria Individual"),
    "explorer_caption":         (
        "Step through individual Monte Carlo paths. Vertical dotted lines mark"
        "each quarterly observation date. Green star = issuer called here.",
        "Navega por trayectorias individuales de Monte Carlo. Las líneas punteadas marcan"
        "cada fecha de observación trimestral. Estrella verde = emisor ejerció el rescate aquí.",
    ),
    "random_path":              ("Random Path",                   "Trayectoria Aleatoria"),
    "prev_path":                ("Previous",                      "Anterior"),
    "next_path":                ("Next",                          "Siguiente"),
    "path_of":                  ("Path #{n} of {total}",            "Trayectoria #{n} de {total}"),
    "asset_price_paths":        ("Asset Price Paths — Path #{n}",   "Trayectorias de Precios — Trayectoria #{n}"),
    "price_label":              ("Price",                            "Precio"),
    "time_step":                ("Time Step",                        "Paso de Tiempo"),
    "wof_path_title":           ("Worst-of Performance Path #{n}",  "Trayectoria de Rendimiento Worst-of #{n}"),
    "nominal_payout":           ("Nominal Payout",                  "Pago Nominal"),
    "annualised_return":        ("Annualised Return",               "Rendimiento Anualizado"),
    "called_label":             ("← Called",                        "← Rescatada"),
    "continued_label":          ("(continued)",                     "(continúa)"),
    "outcome_called":           ("Issuer called at {q}",         "Emisor rescató la nota en {q}"),
    "outcome_upside":           ("Reached maturity — upside participation",
                                 "Llegó al vencimiento — participación al alza"),
    "outcome_floor":            ("Reached maturity — capital floor applied",
                                 "Llegó al vencimiento — piso de capital activado"),

    # ── Tab 4 — Correlation ────────────────────────────────────────────────
    "corr_subheader":           ("Correlation Diagnostics",          "Diagnóstico de Correlaciones"),
    "corr_caption":             (
        "**Input** correlations are estimated from historical data. "
        "**Realized** correlations are from the simulated paths — they should be"
        "close to the inputs, validating the Cholesky structure.",
        "Las correlaciones de **entrada** se estiman de datos históricos. "
        "Las correlaciones **realizadas** se calculan de las trayectorias simuladas — deben estar"
        "cerca de los valores de entrada, validando la estructura de Cholesky.",
    ),
    "input_calibrated":         ("Input (Calibrated)",               "Entrada (Calibrada)"),
    "realized_simulated":       ("Realized (Simulated)",             "Realizada (Simulada)"),
    "diff_label":               ("Difference (Realized − Input)",    "Diferencia (Realizada − Entrada)"),
    "corr_ok":                  ("Max off-diagonal error: **{v:.4f}** — correlation structure well reproduced.",
                                 "Error máximo fuera de la diagonal: **{v:.4f}** — estructura de correlación bien reproducida."),
    "corr_warn":                ("Max off-diagonal error: **{v:.4f}** — consider increasing n_paths.",
                                 "Error máximo fuera de la diagonal: **{v:.4f}** — considere aumentar el número de trayectorias de Monte Carlo."),
    "heston_params":            ("Calibrated Heston Parameters",     "Parámetros Heston Calibrados"),
    "heston_params_caption":    ("Estimated from historical price data via Method of Moments.",
                                 "Estimados de datos históricos de precios mediante el Método de Momentos."),
    "asset":                    ("Asset",                            "Activo"),
    "mu_label":                 ("μ (drift p.a.)",                  "μ (drift anual)"),
    "v0_label":                 ("V₀ (σ)",                          "V₀ (σ)"),
    "theta_label":              ("θ (long-run σ)",                  "θ (σ largo plazo)"),
    "kappa_label":              ("κ (mean rev.)",                   "κ (rev. media)"),
    "t_copula_info":            (
        "**Student-t Copula:** ν = {v} degrees of freedom, "
        "fitted from the historical return distribution of each asset. "
        "Captures joint tail dependence — the tendency for all three indices"
        "to fall simultaneously in stress scenarios.",
        "**Cópula Student-t:** ν = {v} grados de libertad, "
        "ajustados a partir de la distribución histórica de retornos de cada activo. "
        "Captura la dependencia de colas conjunta — la tendencia de los tres índices"
        "a caer simultáneamente en escenarios de estrés.",
    ),
    "rho_note":                 (
        "**Note on ρ (leverage effect):** Textbook equity models assume ρ ≈ −0.65 for SPX. "
        "The calibration here shows ρ near zero because the 2021–2026 window was a bull"
        "market with low vol-return correlation. This is what the data shows — not a bug. "
        "A risk-neutral calibration from the options surface would recover the expected negative ρ.",
        "**Nota sobre ρ (efecto apalancamiento):** Los modelos canónicos asumen ρ ≈ −0.65 para SPX. "
        "La calibración aquí muestra ρ cercano a cero porque la ventana 2021–2026 fue alcista"
        "con baja correlación vol-retorno. Esto es lo que muestran los datos — no es un error. "
        "Una calibración risk-neutral desde opciones recuperaría el ρ negativo esperado.",
    ),

    # ── Note structure expander ────────────────────────────────────────────
    "note_structure_expander": ("Note Structure Summary",         "Resumen de la Estructura de la Nota"),
    "underlyings_header":        ("**Underlyings**",                   "**Subyacentes**"),
    "col_display_name":          ("Display Name",                      "Nombre"),
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
    "best_of_rescue_info":       (
        "**Best-of capital rescue:** at maturity, capital is returned at par if the"
        "best performer finishes ≥ {barrier:.0%} of initial, even if the knock-in barrier was breached.",
        "**Rescate best-of de capital:** al vencimiento, el capital se devuelve a la par si el"
        "mejor subyacente termina ≥ {barrier:.0%} del inicial, incluso si la barrera knock-in fue tocada.",
    ),

    # ── MC tab — top-level ─────────────────────────────────────────────────
    "summary_stats_header":      ("Summary Statistics",                "Estadísticas Resumen"),
    "expected_irr_pa":           ("Expected IRR p.a. (simple)",        "TIR Esperada p.a. (simple)"),
    "expected_total_return":     ("Expected Total Return",             "Rendimiento Total Esperado"),
    "expected_coupon_metric":    ("Expected Coupon",                   "Cupón Esperado"),
    "prob_autocalled":           ("P(Autocalled)",                     "P(Autocall)"),
    "prob_knock_in_metric":      ("P(Knock-in)",                       "P(Knock-in)"),
    "barrier_rescued_caption":   (
        "Barrier breached on {barrier:.2%} of paths; {rescued:.2%} were rescued to par by the"
        "final redemption condition ({basket} ≥ {level:.0%}).",
        "Barrera tocada en el {barrier:.2%} de trayectorias; {rescued:.2%} fueron rescatadas a la par por"
        "la condición de redención final ({basket} ≥ {level:.0%}).",
    ),
    "autocall_by_period_expander": ("Autocall probability by period", "Probabilidad de autocall por período"),
    "col_eligible":              ("Eligible",                          "Elegible"),
    "col_p_autocall":            ("P(autocall)",                       "P(autocall)"),

    # ── MC sub-tabs ────────────────────────────────────────────────────────
    "mc_subtab_payoff":          ("Payoff & Distribution",          "Payoff y Distribución"),
    "mc_subtab_paths":           ("Price Paths",                    "Trayectorias de Precio"),
    "mc_subtab_explorer":        ("Path Explorer",                  "Explorador de Trayectorias"),
    "mc_subtab_corr":            ("Correlation Diagnostics",        "Diagnóstico de Correlaciones"),

    # ── MC tab1 — IRR distribution ─────────────────────────────────────────
    "irr_dist_subheader":        ("IRR Distribution — All Simulated Paths",
                                  "Distribución de TIR — Todas las Trayectorias Simuladas"),
    "knock_in_info":             (
        "**{pct:.1%}** of paths trigger the knock-in barrier ({barrier:.0%}) at maturity.",
        "**{pct:.1%}** de las trayectorias activan la barrera knock-in ({barrier:.0%}) al vencimiento.",
    ),

    # ── MC tab2 — price paths ──────────────────────────────────────────────
    "price_paths_subheader":     ("Simulated Price Path Fan Charts",   "Abanicos de Trayectorias de Precio Simuladas"),
    "wof_basket_md":             ("#### Worst-of Basket Performance",  "#### Rendimiento de la Cesta Worst-of"),
    "individual_paths_md":       ("#### Individual Underlying Paths",  "#### Trayectorias Individuales de Subyacentes"),

    # ── MC tab3 — path explorer ────────────────────────────────────────────
    "single_path_subheader":     ("Single Path Explorer",              "Explorador de Trayectoria Individual"),
    "path_caption":              ("Path #{n} of {total}",              "Trayectoria #{n} de {total}"),
    "autocalled_at_md":          ("### Autocalled at period {q} ({t:.3g}Y)",
                                  "### Autocall en período {q} ({t:.3g}A)"),
    "maturity_knock_in_md":      ("### Maturity — Knock-in (worst-of: {wof:.1%})",
                                  "### Vencimiento — Knock-in (worst-of: {wof:.1%})"),
    "maturity_no_knock_in_md": ("### Maturity — No knock-in (worst-of: {wof:.1%})",
                                  "### Vencimiento — Sin knock-in (worst-of: {wof:.1%})"),
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
    "live_metric_wof_today":     ("Worst-of Today",                    "Worst-of Hoy"),
    "live_metric_vs_strike":     ("{v:.1%} vs strike",                 "{v:.1%} vs strike"),
    "live_metric_worst_asset":   ("Worst Asset",                       "Activo Más Débil"),
    "live_metric_vs_ki":         ("vs KI Barrier",                     "vs Barrera KI"),
    "live_metric_vs_autocall":   ("vs Autocall",                       "vs Autocall"),
    "live_asset_perf_header":    ("#### Current Asset Performance",    "#### Rendimiento Actual por Activo"),
    "live_obs_history_header":   ("#### Observation History",          "#### Historial de Observaciones"),
    "live_col_period":           ("Period",                            "Período"),
    "live_col_date":             ("Date",                              "Fecha"),
    "live_col_status":           ("Status",                            "Estado"),
    "live_col_wof":              ("Worst-of",                          "Worst-of"),
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
    "backtest_header":          ("Historical Backtest",           "Backtest Histórico"),
    "backtest_intro":           (
        "Evaluates how this note would have performed if issued on every available"
        "date between **June 2022** and **June 2025**, using actual realized index prices. "
        "No simulation — just the real historical path. "
        "Results update automatically when you change the coupon, floor, or decisiveness sliders.",
        "Evalúa cómo habría funcionado esta nota si se hubiera emitido en cada fecha disponible"
        "entre **junio 2022** y **junio 2025**, usando los precios reales de los índices. "
        "Sin simulación — solo la trayectoria histórica real. "
        "Los resultados se actualizan automáticamente al cambiar los sliders.",
    ),
    "running_backtest":         ("Running historical backtest...",   "Ejecutando backtest histórico..."),
    "backtest_failed":          ("Backtest failed: {e}",            "El backtest falló: {e}"),
    "backtest_no_results":      (
        "No backtest results — check that SPX.csv, SX5E.csv, SMI.csv are present.",
        "Sin resultados de backtest — verifique que SPX.csv, SX5E.csv, SMI.csv estén presentes.",
    ),
    "issue_dates_header":       ("### Across All Historical Issue Dates",
                                 "### Para Todas las Fechas de Emisión Históricas"),
    "issue_dates_tested":       ("Issue Dates Tested",              "Fechas de Emisión"),
    "mean_irr":                 ("Mean IRR",                        "TIR Promedio"),
    "median_irr":               ("Median IRR",                      "TIR Mediana"),
    "floor_triggered":          ("Floor Triggered",                 "Piso Activado"),
    "called_early":             ("Called Early",                    "Rescate Anticipado"),
    "outcome_dist":             ("Outcome Distribution",            "Distribución de Resultados"),
    "count":                    ("Count",                           "Cantidad"),
    "worst_asset_at_mat":       ("Worst-of Asset at Maturity (uncalled notes)",
                                 "Activo Worst-of al Vencimiento (notas no rescatadas)"),
    "irr_by_issue":             ("### Annualised Return by Issue Date",
                                 "### TIR Anualizada por Fecha de Emisión"),
    "irr_by_issue_caption":     ("Each point is one historical issue date. Color shows the note outcome.",
                                 "Cada punto es una fecha de emisión histórica. El color muestra el resultado."),
    "realised_irr_title":       ("Realised IRR by Issue Date",      "TIR Realizada por Fecha de Emisión"),
    "break_even":               ("Break-even",                      "Break-even"),
    "hist_paths_header":        ("### Historical Price Paths",       "### Trayectorias Históricas de Precio"),
    "hist_paths_caption":       (
        "Actual index levels over the full data history. "
        "Vertical lines mark the start and end of the valid backtest window.",
        "Niveles reales de los índices durante todo el historial de datos. "
        "Las líneas verticales marcan el inicio y fin de la ventana de backtest válida.",
    ),
    "backtest_start":           ("Backtest start",                  "Inicio backtest"),
    "backtest_end":             ("Backtest end",                    "Fin backtest"),
    "normalised_level":         ("Normalised Level (base=100)",     "Nivel Normalizado (base=100)"),
    "date_axis":                ("Date",                            "Fecha"),
    "wof_hist_header":          ("### Historical Worst-of Performance",
                                 "### Rendimiento Histórico Worst-of"),
    "wof_hist_caption":         (
        "Worst-performing index at each date relative to a rolling 1-year initial level.",
        "Índice de peor rendimiento en cada fecha relativo a un nivel inicial móvil de 1 año.",
    ),
    "wof_1y_rolling":           ("Worst-of (1Y rolling)",           "Worst-of (móvil 1A)"),
    "no_change":                ("No change",                       "Sin cambio"),

    # ── Outcome labels (used in bt["Outcome"]) ─────────────────────────────
    "outcome_maturity":         ("Maturity",                        "Vencimiento"),
    "outcome_called_3m":        ("Called at 3M",                    "Rescate en 3M"),
    "outcome_called_6m":        ("Called at 6M",                    "Rescate en 6M"),
    "outcome_called_9m":        ("Called at 9M",                    "Rescate en 9M"),
    "outcome_floor_applied":    ("Floor Applied",                   "Piso Activado"),

    # ── Misc ───────────────────────────────────────────────────────────────
    "sim_spinner":              ("Running Heston calibration and Monte Carlo simulation...",
                                 "Ejecutando calibración Heston y simulación de Monte Carlo..."),
    "configure_sidebar":        (
        "Configure parameters in the sidebar and click **Run Simulation** to begin.",
        "Configure los parámetros en la barra lateral y haga clic en **Ejecutar Simulación** para comenzar.",
    ),
    "called_at_obs":            ("Worst-of was **{perf:.1%}** at observation. Note redeemed after **{t:.2g} years**.",
                                 "El worst-of era **{perf:.1%}** en la observación. Nota rescatada tras **{t:.2g} años**."),
    "upside_detail":            ("Worst-of finished at **{perf:.1%}**, above the floor.",
                                 "El worst-of cerró en **{perf:.1%}**, por encima del piso de capital."),
    "floor_detail":             ("Worst-of finished at **{perf:.1%}**, below the {floor:.0%} floor.",
                                 "El worst-of cerró en **{perf:.1%}**, por debajo del piso de capital de {floor:.0%}."),
    "floor_info":               (
        "**{pct:.1%}** of simulated paths reach maturity with the worst-of below {floor:.0%}%, "
        "triggering the capital floor.",
        "**{pct:.1%}** de las trayectorias simuladas llegan al vencimiento con el worst-of por debajo de {floor:.0%}%, "
        "activando el piso de capital.",
    ),
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
