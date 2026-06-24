/* UI-chrome strings for the React shell (labels, buttons, headings). The Plotly
   figures themselves are translated server-side via the `lang` param, so this
   only covers the new front-end's own text. Mirrors the EN/ES split of
   app/translations.py for the labels we surface here. */
export type Lang = 'en' | 'es'

type Dict = Record<string, { en: string; es: string }>

export const S: Dict = {
  app_title:        { en: 'Structured note simulator', es: 'Simulador de notas estructuradas' },
  worst_of:         { en: 'worst-of', es: 'peor de' },

  // setup rail
  setup_heading:    { en: 'Note setup', es: 'Configuración' },
  config_label:     { en: 'Term sheet', es: 'Ficha técnica' },
  underlyings:      { en: 'Underlyings', es: 'Subyacentes' },
  add_underlying:   { en: 'Add underlying…', es: 'Añadir subyacente…' },
  add_custom:       { en: 'Custom ticker', es: 'Ticker personalizado' },
  ul_symbol:        { en: 'Symbol', es: 'Símbolo' },
  ul_name:          { en: 'Display name', es: 'Nombre' },
  add_btn:          { en: 'Add', es: 'Añadir' },
  max_underlyings:  { en: 'Maximum 5 underlyings.', es: 'Máximo 5 subyacentes.' },

  // sections
  sec_basket:       { en: 'Basket & overlays', es: 'Cesta y overlays' },
  sec_autocall:     { en: 'Autocall schedule', es: 'Programa de autocancelación' },
  sec_protection:   { en: 'Protection', es: 'Protección' },
  sec_metadata:     { en: 'Issuer & dates', es: 'Emisor y fechas' },
  sec_engine:       { en: 'Engine', es: 'Motor' },

  // advanced term fields
  coupon_basket:    { en: 'Coupon basket', es: 'Cesta de cupón' },
  autocall_basket:  { en: 'Autocall basket', es: 'Cesta de autocancelación' },
  basket_worst_of:  { en: 'Worst-of', es: 'Peor de' },
  basket_best_of:   { en: 'Best-of', es: 'Mejor de' },
  basket_average:   { en: 'Average', es: 'Promedio' },
  one_star:         { en: 'One-Star overlay', es: 'Overlay One-Star' },
  one_star_level:   { en: 'One-Star level', es: 'Nivel One-Star' },
  step_down:        { en: 'Step-down per period', es: 'Reducción por periodo' },
  autocall_floor:   { en: 'Autocall floor', es: 'Suelo de autocancelación' },
  premium_at_call:  { en: 'Premium at call only', es: 'Prima solo al llamar' },
  min_return:       { en: 'Minimum return', es: 'Retorno mínimo' },
  capital_protected:{ en: 'Capital protection', es: 'Protección de capital' },
  capital_guarantee:{ en: 'Capital guarantee', es: 'Garantía de capital' },
  cap_upside:       { en: 'Cap the upside', es: 'Limitar la subida' },
  upside_cap:       { en: 'Upside cap', es: 'Tope de subida' },
  note_name:        { en: 'Note name', es: 'Nombre de la nota' },
  issuer_name:      { en: 'Issuer', es: 'Emisor' },
  rating_sp:        { en: 'S&P', es: 'S&P' },
  rating_moody:     { en: "Moody's", es: "Moody's" },
  rating_fitch:     { en: 'Fitch', es: 'Fitch' },
  issue_date:       { en: 'Issue date', es: 'Fecha de emisión' },
  seed:             { en: 'Random seed', es: 'Semilla aleatoria' },
  calib_window:     { en: 'Calibration window', es: 'Ventana de calibración' },
  calib_years:      { en: 'years', es: 'años' },
  maturity:         { en: 'Maturity', es: 'Vencimiento' },
  coupon_pa:        { en: 'Coupon p.a.', es: 'Cupón anual' },
  frequency:        { en: 'Frequency', es: 'Frecuencia' },
  coupon_barrier:   { en: 'Coupon barrier', es: 'Barrera de cupón' },
  autocall_barrier: { en: 'Autocall barrier', es: 'Barrera de autocancelación' },
  knock_in_barrier: { en: 'Knock-in barrier', es: 'Barrera de knock-in' },
  autocall_start:   { en: 'Autocall starts', es: 'Autocancelación desde' },
  memory:           { en: 'Memory coupons', es: 'Cupones con memoria' },
  paths:            { en: 'Paths', es: 'Trayectorias' },
  engine:           { en: 'Engine', es: 'Motor' },
  run:              { en: 'Run simulation', es: 'Ejecutar simulación' },
  rerun:            { en: 'Re-run', es: 'Re-ejecutar' },
  running:          { en: 'Running…', es: 'Ejecutando…' },

  // frequencies
  freq_monthly:     { en: 'Monthly', es: 'Mensual' },
  freq_quarterly:   { en: 'Quarterly', es: 'Trimestral' },
  'freq_semi-annual': { en: 'Semi-annual', es: 'Semestral' },
  freq_annual:      { en: 'Annual', es: 'Anual' },

  // structure
  note_structure:   { en: 'Note structure', es: 'Estructura de la nota' },
  live_updates:     { en: 'updates as you edit terms', es: 'se actualiza al editar' },
  issue:            { en: 'issue', es: 'emisión' },
  maturity_short:   { en: 'maturity', es: 'venc.' },
  autocall_window:  { en: 'autocall window', es: 'ventana de autocancelación' },

  // hero metrics
  expected_irr:     { en: 'Expected IRR', es: 'TIR esperada' },
  p_autocall:       { en: 'P(autocall)', es: 'P(autocancelación)' },
  p_knock_in:       { en: 'P(knock-in)', es: 'P(knock-in)' },
  exp_payout:       { en: 'Expected payout', es: 'Pago esperado' },
  per_100:          { en: 'per 100 nominal', es: 'por 100 nominal' },
  vs_coupon:        { en: 'coupon p.a.', es: 'cupón anual' },

  // outcomes / waterfall
  outcomes:         { en: 'Outcome breakdown', es: 'Desglose de resultados' },
  autocalled_at:    { en: 'Autocalled', es: 'Autocancelado' },
  held_to_mat:      { en: 'Held to maturity', es: 'Hasta vencimiento' },
  redeemed_par:     { en: 'Redeemed at par', es: 'Redimido a la par' },
  knocked_in:       { en: 'Knocked in', es: 'Knock-in' },
  period:           { en: 'Period', es: 'Periodo' },

  // tabs
  tab_mc:           { en: 'Monte Carlo', es: 'Monte Carlo' },
  tab_backtest:     { en: 'Historical backtest', es: 'Backtest histórico' },
  tab_live:         { en: 'Current performance', es: 'Rendimiento actual' },
  tab_report:       { en: 'Report', es: 'Informe' },

  // chart panel titles
  irr_distribution: { en: 'IRR distribution', es: 'Distribución de TIR' },
  worst_of_fan:     { en: 'Worst-of fan', es: 'Abanico del peor de' },
  per_asset:        { en: 'Per-asset fans', es: 'Abanicos por activo' },
  correlation:      { en: 'Correlation', es: 'Correlación' },
  corr_input:       { en: 'Input (historical)', es: 'Entrada (histórica)' },
  corr_realized:    { en: 'Realized (simulated)', es: 'Realizada (simulada)' },

  // status / staleness
  status_current:   { en: 'Up to date', es: 'Actualizado' },
  status_stale:     { en: 'Stale', es: 'Desactualizado' },
  stale_banner:     { en: 'Inputs changed since this run — re-run to refresh the results.', es: 'Los parámetros cambiaron desde esta simulación — vuelve a ejecutar para actualizar.' },
  sub_summary:      { en: 'Summary', es: 'Resumen' },
  sub_fans:         { en: 'Distributions', es: 'Distribuciones' },
  sub_correlation:  { en: 'Correlation', es: 'Correlación' },
  sub_explorer:     { en: 'Path explorer', es: 'Explorador' },

  // backtest
  bt_issues:        { en: 'Historical issues', es: 'Emisiones históricas' },
  bt_mean_irr:      { en: 'Mean IRR', es: 'TIR media' },
  bt_median_irr:    { en: 'Median IRR', es: 'TIR mediana' },
  bt_called_rate:   { en: 'Autocall rate', es: 'Tasa de autocancelación' },
  bt_ki_rate:       { en: 'Knock-in rate', es: 'Tasa de knock-in' },
  bt_outcomes:      { en: 'Outcome distribution', es: 'Distribución de resultados' },
  bt_table:         { en: 'Issue-by-issue', es: 'Emisión por emisión' },
  bt_empty:         { en: 'No historical issues for this configuration — the underlyings may not have enough overlapping history.', es: 'No hay emisiones históricas para esta configuración — puede que los subyacentes no tengan suficiente historia común.' },
  bt_intro:         { en: 'Replays this note over every historical start date with enough remaining data, using realized prices.', es: 'Reproduce esta nota en cada fecha de inicio histórica con datos suficientes, usando precios reales.' },
  col_date:         { en: 'Issue date', es: 'Fecha de emisión' },
  col_outcome:      { en: 'Outcome', es: 'Resultado' },
  col_worst:        { en: 'Worst asset', es: 'Peor activo' },
  col_worst_perf:   { en: 'Worst final', es: 'Peor final' },
  col_irr:          { en: 'IRR p.a.', es: 'TIR anual' },
  run_backtest:     { en: 'Run backtest', es: 'Ejecutar backtest' },

  // path explorer
  explorer_intro:   { en: 'A random sample of simulated worst-of paths, coloured by outcome. Filter below; drag on the chart to zoom.', es: 'Una muestra aleatoria de trayectorias del peor de, coloreadas por resultado. Filtra abajo; arrastra en el gráfico para hacer zoom.' },
  filter_all:       { en: 'All', es: 'Todas' },
  explorer_showing: { en: 'Showing', es: 'Mostrando' },
  explorer_of:      { en: 'of', es: 'de' },
  explorer_sampled: { en: 'sampled paths', es: 'trayectorias muestreadas' },
  explorer_resample:{ en: 'Resample', es: 'Re-muestrear' },
  explorer_expired: { en: 'This run expired from the server cache — re-run the simulation to explore paths.', es: 'Esta simulación expiró de la caché del servidor — vuelve a ejecutar para explorar trayectorias.' },
  chart_time_years: { en: 'Time (years)', es: 'Tiempo (años)' },
  chart_wof:        { en: 'Worst-of performance', es: 'Rendimiento del peor de' },

  // states
  loading:          { en: 'Loading…', es: 'Cargando…' },
  no_run_title:     { en: 'No simulation yet', es: 'Aún no hay simulación' },
  no_run_body:      { en: 'Pick a term sheet and hit Run to price the note across thousands of Monte-Carlo paths.', es: 'Elige una ficha y pulsa Ejecutar para valorar la nota sobre miles de trayectorias Monte-Carlo.' },
  calibrating:      { en: 'Calibrating', es: 'Calibrando' },
  simulating:       { en: 'Simulating paths', es: 'Simulando trayectorias' },
  pricing:          { en: 'Pricing payoff', es: 'Valorando' },
  error:            { en: 'Something went wrong', es: 'Algo salió mal' },
  coming_soon:      { en: 'Coming soon', es: 'Próximamente' },
}

export function makeT(lang: Lang) {
  return (key: string): string => {
    const e = S[key]
    if (!e) return key
    return e[lang] ?? e.en
  }
}
