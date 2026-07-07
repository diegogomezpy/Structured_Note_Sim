/* Shared report-section catalogue + audience presets.
   Single source of truth for BOTH the single-note Report panel and the Batch
   panel, so the two never drift. Item = [key, EN label, ES label]. */

export type Item = [key: string, en: string, es: string]
export type Group = { key: string; en: string; es: string; items: Item[] }

export const TREE: Group[] = [
  { key: 'note', en: 'Note details', es: 'Detalle de la nota', items: [
    ['cover', 'Cover page', 'Portada'],
    ['note_description', 'Note description', 'Descripción de la nota'],
    ['note_diagram', 'Structure diagram', 'Diagrama de la estructura'],
    ['note_terms', 'Note terms', 'Términos'],
    ['obs_schedule', 'Observation schedule', 'Calendario de observaciones'],
    ['issuer_info', 'Issuer information', 'Información del emisor'],
    ['underlying_breakdown', 'Underlying breakdown', 'Análisis de subyacentes'],
  ] },
  { key: 'mc', en: 'Monte Carlo', es: 'Monte Carlo', items: [
    ['mc_metrics', 'Summary & metrics', 'Resumen y métricas'],
    ['mc_outcome', 'Outcome breakdown', 'Distribución de resultados'],
    ['mc_autocall', 'Autocall by period', 'Autocall por período'],
    ['mc_irr', 'IRR distribution', 'Distribución de TIR'],
    ['mc_wof', 'Worst-of fan chart', 'Abanico del peor de'],
    ['mc_sample', 'Sample paths', 'Trayectorias de muestra'],
    ['mc_fans', 'Per-underlying fans', 'Abanicos por activo'],
    ['calib_corr', 'Correlation diagnostics', 'Diagnóstico de correlación'],
    ['calib_table', 'Calibration table', 'Tabla de calibración'],
  ] },
  { key: 'bt', en: 'Historical backtest', es: 'Backtest histórico', items: [
    ['bt_metrics', 'Outcome metrics', 'Métricas de resultados'],
    ['bt_outcome', 'Outcome distribution', 'Distribución de resultados'],
    ['bt_pie', 'Worst-asset pie', 'Peor activo'],
    ['bt_irr', 'IRR scatter', 'Dispersión de TIR'],
    ['bt_prices', 'Price history', 'Histórico de precios'],
  ] },
  { key: 'live', en: 'Current performance', es: 'Rendimiento actual', items: [
    ['live_metrics', 'Live metrics', 'Métricas en vivo'],
    ['live_asset_table', 'Per-asset table', 'Tabla por activo'],
    ['live_obs_table', 'Observation history', 'Historial de observaciones'],
    ['live_chart', 'Performance chart', 'Gráfico de rendimiento'],
  ] },
]

// Report presets — one click selects a sensible set of sections for an audience.
// Keys are intersected with what's actually available (e.g. the live group only
// when the note has an issue date). "full" / "custom" are handled specially.
export const PRESET_KEYS: Record<string, string[]> = {
  client: ['cover', 'note_description', 'note_diagram', 'note_terms', 'obs_schedule', 'issuer_info', 'underlying_breakdown'],
  term_sheet: ['cover', 'note_terms', 'note_diagram', 'obs_schedule', 'issuer_info'],
  marketing: ['cover', 'note_description', 'note_diagram', 'underlying_breakdown', 'mc_metrics', 'mc_outcome', 'live_metrics', 'live_chart'],
  ic: ['note_terms', 'note_diagram', 'underlying_breakdown', 'mc_metrics', 'mc_outcome', 'mc_autocall', 'mc_wof', 'bt_metrics', 'bt_outcome', 'live_metrics'],
  analyst: ['note_terms', 'note_diagram', 'obs_schedule', 'issuer_info', 'underlying_breakdown',
            'mc_metrics', 'mc_outcome', 'mc_autocall', 'mc_irr', 'mc_wof', 'mc_sample', 'mc_fans', 'calib_corr', 'calib_table',
            'bt_metrics', 'bt_outcome', 'bt_pie', 'bt_irr', 'bt_prices',
            'live_metrics', 'live_asset_table', 'live_obs_table', 'live_chart'],
  quant: ['note_terms', 'mc_metrics', 'mc_irr', 'mc_wof', 'mc_fans', 'calib_corr', 'calib_table'],
}
export const PRESET_ORDER = ['full', 'client', 'term_sheet', 'marketing', 'ic', 'analyst', 'quant', 'custom'] as const
export type Preset = (typeof PRESET_ORDER)[number]

/** Groups available for a note — the live group only when it has an issue date. */
export function groupsFor(hasLive: boolean): Group[] {
  return TREE.filter((g) => g.key !== 'live' || hasLive)
}

/** Flat list of every item key across the given groups (render order). */
export function keysOf(groups: Group[]): string[] {
  return groups.flatMap((g) => g.items.map((i) => i[0]))
}

/** Section keys a preset selects, intersected with what's available. `full`
    selects everything; `custom` is caller-managed (returns the current keys). */
export function keysForPreset(preset: Preset, allKeys: string[]): string[] {
  if (preset === 'full' || preset === 'custom') return allKeys
  return (PRESET_KEYS[preset] ?? []).filter((k) => allKeys.includes(k))
}
