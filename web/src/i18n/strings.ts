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
