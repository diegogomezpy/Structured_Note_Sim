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
    ['mc_single_wof', 'Selected path(s)', 'Trayectoria(s) seleccionada(s)'],
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

// Report presets — one click selects a set of sections for an audience. Keys are
// intersected with what's actually available (e.g. the live group only when the
// note has an issue date). "full" (everything) and "custom" (free-form) are
// special and not editable as definitions.
//
// These are DEFAULTS: the user can redefine what each audience preset includes
// (see loadPresetOverrides / savePresetOverride). Every consumer reads the
// definitions through presetKeys() / keysForPreset(), so an edit applies to the
// Report panel and the Batch panel alike.
export const DEFAULT_PRESET_KEYS: Record<string, string[]> = {
  advisor: ['cover', 'note_description', 'note_diagram', 'note_terms', 'obs_schedule',
            'underlying_breakdown', 'mc_metrics', 'mc_outcome', 'live_metrics', 'live_chart'],
  client: ['cover', 'note_description', 'note_diagram', 'note_terms', 'obs_schedule', 'issuer_info', 'underlying_breakdown'],
  ic: ['note_terms', 'note_diagram', 'underlying_breakdown', 'mc_metrics', 'mc_outcome', 'mc_autocall',
       'mc_wof', 'bt_metrics', 'bt_outcome', 'live_metrics'],
  risk: ['note_terms', 'note_diagram', 'issuer_info',
         'mc_metrics', 'mc_outcome', 'mc_autocall', 'mc_irr', 'mc_wof', 'mc_fans', 'calib_corr', 'calib_table',
         'bt_metrics', 'bt_outcome', 'bt_pie', 'bt_irr',
         'live_metrics', 'live_obs_table'],
}
export const PRESET_ORDER = ['full', 'advisor', 'client', 'ic', 'risk', 'custom'] as const
export type Preset = (typeof PRESET_ORDER)[number]
/** Presets whose section list the user can redefine (full/custom are special). */
export const EDITABLE_PRESETS = PRESET_ORDER.filter(
  (p) => p !== 'full' && p !== 'custom') as Exclude<Preset, 'full' | 'custom'>[]

// ── user-defined preset contents (persisted) ─────────────────────────────────
const PRESETS_LS = 'mercator_report_presets'

export function loadPresetOverrides(): Record<string, string[]> {
  try { const r = localStorage.getItem(PRESETS_LS); return r ? JSON.parse(r) as Record<string, string[]> : {} }
  catch { return {} }
}
/** The section keys a preset is defined as — the user's override, else the default. */
export function presetKeys(p: string): string[] {
  return loadPresetOverrides()[p] ?? DEFAULT_PRESET_KEYS[p] ?? []
}
/** Redefine a preset. Only the keys the user chose are stored, so a later change
    to a DEFAULT never silently overwrites their definition. */
export function savePresetOverride(p: string, keys: string[]): void {
  try {
    const all = loadPresetOverrides()
    all[p] = [...keys]
    localStorage.setItem(PRESETS_LS, JSON.stringify(all))
  } catch { /* ignore */ }
}
/** Drop the user's definition for a preset, restoring the built-in default. */
export function resetPresetOverride(p: string): void {
  try {
    const all = loadPresetOverrides()
    delete all[p]
    localStorage.setItem(PRESETS_LS, JSON.stringify(all))
  } catch { /* ignore */ }
}
export const isPresetCustomised = (p: string): boolean => p in loadPresetOverrides()

// ── active report-section selection (shared with the PDF Studio proof) ───────
// The Report panel mirrors its live section selection here on every change; the
// Studio's live proof reads it so the preview shows exactly the pages that will
// be printed. Distinct from the persisted "custom" selection (which only tracks
// the custom preset) — this always reflects the current selection, whatever the
// active preset.
const ACTIVE_LS = 'mercator_report_sections_active'
export const ACTIVE_SECTIONS_EVENT = 'report-sections-change'
export function saveActiveSections(keys: string[]): void {
  try {
    localStorage.setItem(ACTIVE_LS, JSON.stringify(keys))
    // Same-tab notification: the `storage` event only fires across tabs, so a
    // proof mounted alongside the toggles (Report → Designer sub-tab) needs this.
    window.dispatchEvent(new CustomEvent(ACTIVE_SECTIONS_EVENT, { detail: keys }))
  } catch { /* ignore */ }
}
export function loadActiveSections(): string[] | null {
  try { const r = localStorage.getItem(ACTIVE_LS); return r ? (JSON.parse(r) as string[]) : null }
  catch { return null }
}

/** Groups available for a note — the live group only when it has an issue date. */
export function groupsFor(hasLive: boolean): Group[] {
  return TREE.filter((g) => g.key !== 'live' || hasLive)
}

/** Flat list of every item key across the given groups (render order). */
export function keysOf(groups: Group[]): string[] {
  return groups.flatMap((g) => g.items.map((i) => i[0]))
}

/** Section keys a preset selects, intersected with what's available. `full`
    selects everything; `custom` is caller-managed (returns the current keys).
    Reads the user's definition when they've redefined the preset. */
export function keysForPreset(preset: Preset, allKeys: string[]): string[] {
  if (preset === 'full' || preset === 'custom') return allKeys
  return presetKeys(preset).filter((k) => allKeys.includes(k))
}
