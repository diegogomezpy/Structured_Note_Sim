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
    "pct_5_95":                 ("5th–95th pct",                     "Pct 5–95"),
    "pct_25_75":                ("25th–75th pct",                    "Pct 25–75"),
    "perf_vs_initial":          ("Performance vs Initial",           "Rendimiento vs Inicial"),

    # ── Tab 3 — Path Explorer ──────────────────────────────────────────────
    "asset_price_paths":        ("Asset Price Paths — Path #{n}",   "Trayectorias de Precios — Trayectoria #{n}"),
    "price_label":              ("Price",                            "Precio"),
    "time_step":                ("Time Step",                        "Paso de Tiempo"),
    "wof_path_title":           ("Worst-of Performance Path #{n}",  "Trayectoria de Rendimiento Worst-of #{n}"),
    "called_label":             ("← Called",                        "← Rescatada"),
    "continued_label":          ("(continued)",                     "(continúa)"),

    # ── Tab 4 — Correlation ────────────────────────────────────────────────
    "asset":                    ("Asset",                            "Activo"),

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
    "setup_select_underlyings": ("Select underlyings (2–5)",           "Seleccione subyacentes (2–5)"),
    "setup_add_custom_expander":("Add a custom ticker (not in the list above)",
                                 "Agregar un ticker personalizado (que no esté en la lista anterior)"),
    "setup_custom_caption":     ("Enter any valid yfinance symbol, e.g. UBER, 2222.SR, BTC-USD",
                                 "Ingrese cualquier símbolo válido de yfinance, ej. UBER, 2222.SR, BTC-USD"),
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
    "setup_basket_types":       ("Basket Types",                       "Tipos de Cesta"),
    "setup_coupon_check":       ("Coupon barrier check",               "Comprobación de barrera de cupón"),
    "setup_autocall_check":     ("Autocall trigger check",             "Comprobación del disparador de autocall"),
    "setup_rescue_toggle":      ("Best-of capital rescue at maturity", "Rescate de capital best-of al vencimiento"),
    "setup_rescue_help":        (
        "If ON: even when the knock-in barrier is breached, capital is "
        "returned at 100% as long as the best-performing underlying "
        "finishes at or above the rescue barrier (BBVA-style 'Barrier "
        "and Knock-in' clause). If OFF: standard worst-of redemption — "
        "a knock-in always results in delivery of the worst performer.",
        "Si está activado: incluso si se toca la barrera de knock-in, el capital se "
        "devuelve al 100% siempre que el subyacente de mejor rendimiento termine "
        "en o por encima de la barrera de rescate (cláusula tipo BBVA 'Barrier and "
        "Knock-in'). Si está desactivado: redención worst-of estándar — un knock-in "
        "siempre resulta en la entrega del peor subyacente.",
    ),
    "setup_rescue_barrier":     ("Rescue barrier (% of initial)",      "Barrera de rescate (% del inicial)"),
    "setup_rescue_barrier_help":(
        "Best performer must finish at or above this level for the "
        "rescue to apply. Term sheets typically use 100%.",
        "El mejor subyacente debe terminar en o por encima de este nivel para que "
        "aplique el rescate. Los term sheets suelen usar 100%.",
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

    # ── Basket option labels ───────────────────────────────────────────────
    "basket_worst_of":          ("Worst-of",                           "Peor rendimiento"),
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
        "Run a simulation first to enable it.",
        "Construye el informe, luego aparece un botón de descarga abajo. "
        "Ejecute una simulación primero para habilitarlo.",
    ),
    "sidebar_reconfigure":      ("Reconfigure Note",                   "Reconfigurar Nota"),
    "sidebar_download_pdf":     ("Download PDF",                       "Descargar PDF"),
    "building_pdf":             ("Building PDF report…",               "Construyendo informe PDF…"),

    # ── Dashboard header / structure ───────────────────────────────────────
    "dash_no_memory":           ("No memory",                          "Sin memoria"),
    "dash_memory":              ("Memory",                             "Memoria"),
    "structure_issuer_label":   ("Issuer:",                            "Emisor:"),
    "autocall_eligible_yes":    ("Yes",                                "Sí"),
    "autocall_eligible_coupon_only":("Coupon only",                    "Solo cupón"),

    # ── MC tab — spinners / status ─────────────────────────────────────────
    "mc_run_spinner":           ("Running Heston calibration and Monte Carlo simulation…",
                                 "Ejecutando calibración Heston y simulación de Monte Carlo…"),
    "mc_div_warning":           ("Could not load dividend history ({e}) — simulating without dividend jumps.",
                                 "No se pudo cargar el historial de dividendos ({e}) — simulando sin saltos de dividendos."),
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
        "Probability of capital loss at maturity: knock-in barrier breached "
        "AND the final redemption condition not met. For notes with a best-of "
        "final basket (e.g. BBVA XS3378405743), paths where the best performer "
        "finishes ≥ the redemption barrier are 'rescued' to par even if the "
        "worst breached the KI level — those are excluded here.",
        "Probabilidad de pérdida de capital al vencimiento: barrera de knock-in tocada Y "
        "condición de redención final no cumplida. Para notas con cesta final best-of "
        "(ej. BBVA XS3378405743), las trayectorias donde el mejor subyacente termina ≥ "
        "la barrera de redención son 'rescatadas' a la par aunque el peor haya tocado el "
        "nivel de KI — esas se excluyen aquí.",
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
    "corr_quality_good":        ("good",                               "buena"),
    "corr_quality_acceptable":  ("acceptable",                         "aceptable"),
    "corr_quality_elevated":    ("elevated — consider more paths",     "elevada — considere más trayectorias"),
    "corr_max_err_message":     (
        "Max off-diagonal error: **{err:.4f}** ({quality}). "
        "This is the largest absolute difference between a target and realized "
        "pairwise correlation. Values < 0.05 are acceptable for pricing; "
        "> 0.05 suggests the Cholesky decomposition is not well converged — "
        "try increasing Monte Carlo paths.",
        "Error máximo fuera de la diagonal: **{err:.4f}** ({quality}). Es la mayor "
        "diferencia absoluta entre una correlación objetivo y la realizada por pares. "
        "Valores < 0.05 son aceptables para valoración; > 0.05 sugiere que la "
        "descomposición de Cholesky no convergió bien — intente aumentar las "
        "trayectorias de Monte Carlo.",
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
        "The underlying currently dragging the worst-of basket — "
        "i.e. the one with the lowest performance relative to its "
        "initial fixing. This asset sets the barrier observation level.",
        "El subyacente que actualmente arrastra la cesta worst-of — es decir, el de menor "
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
    "chart_worst_of":            ("Worst-of",                          "Worst-of"),
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
