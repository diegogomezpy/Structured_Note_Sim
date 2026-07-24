import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { useToast } from './Toast'
import Panel from './Panel'
import Icon from './Icon'
import { useTour, reportTour } from './Tour'
import ReportImages from './ReportImages'
import BrandConfigBar from './BrandConfigBar'
import type { Branding, NoteTerms } from '../api/types'
import type { BrandingStudio } from '../lib/useBrandingStudio'
import type { RunOpts } from './SetupRail'
import { TREE, PRESET_ORDER, presetKeys, savePresetOverride, resetPresetOverride,
         isPresetCustomised, saveActiveSections, type Preset, type Group } from '../lib/reportSections'

type Status = 'idle' | 'running' | 'done' | 'error'

const CUSTOM_LS = 'mercator_report_custom'
const loadCustom = (): string[] | null => {
  try { const r = localStorage.getItem(CUSTOM_LS); return r ? (JSON.parse(r) as string[]) : null } catch { return null }
}

function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get('Content-Disposition') || ''
  const m = cd.match(/filename="?([^"]+)"?/)
  return m ? m[1] : fallback
}

function Check({ on, indeterminate }: { on: boolean; indeterminate?: boolean }) {
  return (
    <span style={{
      width: 18, height: 18, borderRadius: 6, flexShrink: 0,
      border: `1.5px solid ${on || indeterminate ? 'var(--accent)' : 'var(--border-strong)'}`,
      background: on || indeterminate ? 'var(--accent)' : 'transparent',
      display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff',
    }}>{on ? <Icon name="check" size={12} /> : indeterminate ? <span style={{ width: 8, height: 2, background: '#fff', borderRadius: 1 }} /> : null}</span>
  )
}

export default function ReportPanel({ terms, opts, variantB, pathImages, brand, studio, onOpenDesigner }: {
  terms: NoteTerms; opts: RunOpts; variantB?: NoteTerms | null
  pathImages?: { title: string; png: string }[]   // path-explorer selection(s) → report
  brand: Branding                                  // owned by ReportView; sent in the request
  studio: BrandingStudio                           // shared branding state (per-report images)
  onOpenDesigner?: () => void                      // jump to the PDF Designer sub-tab
}) {
  const { t, lang } = useI18n()
  const toast = useToast()
  const { start: startTour } = useTour()
  // Include the A/B comparison in the PDF (only offered once a Note B is set up
  // in the Compare tab). Default on when B exists, so building the report after a
  // comparison carries it through.
  const [compareOn, setCompareOn] = useState(true)
  const hasLive = !!terms.issue_date
  const groups = useMemo(() => TREE.filter((g) => g.key !== 'live' || hasLive), [hasLive])
  const allKeys = useMemo(() => groups.flatMap((g) => g.items.map((i) => i[0])), [groups])

  // A saved custom selection (persisted) is restored on load, so the user's own
  // section choice survives across sessions.
  const savedCustom = useMemo(() => loadCustom(), [])
  const [sel, setSel] = useState<Set<string>>(() =>
    new Set(savedCustom ? savedCustom.filter((k) => allKeys.includes(k)) : allKeys))
  const [preset, setPreset] = useState<Preset>(savedCustom ? 'custom' : 'full')
  // Bumped when a preset definition is saved/reset — preset definitions live in
  // localStorage, so this is what tells the memo below to re-read them.
  const [presetRev, setPresetRev] = useState(0)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')

  const lab = (en: string, es: string) => (lang === 'es' ? es : en)
  // Editing sections under an audience preset REDEFINES that preset (once saved)
  // rather than silently dropping to "custom" — the preset is the user's own
  // template. `full` has nothing to redefine, so editing it means going custom.
  const afterEdit = () => { if (preset === 'full') setPreset('custom'); setStatus('idle') }
  const toggle = (k: string) => {
    setSel((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n })
    afterEdit()
  }
  const toggleGroup = (g: Group) => {
    const ks = g.items.map((i) => i[0])
    const allOn = ks.every((k) => sel.has(k))
    setSel((p) => { const n = new Set(p); ks.forEach((k) => allOn ? n.delete(k) : n.add(k)); return n })
    afterEdit()
  }
  // Apply a named preset: select its sections (intersected with what's available).
  // "Custom" restores the saved custom selection (or, if none, keeps the current
  // one so the user can start fine-tuning from where they are).
  const applyPreset = (p: Preset) => {
    setPreset(p)
    setStatus('idle')
    if (p === 'custom') {
      const saved = loadCustom()
      if (saved) setSel(new Set(saved.filter((k) => allKeys.includes(k))))
      return
    }
    setSel(new Set(p === 'full' ? allKeys : presetKeys(p).filter((k) => allKeys.includes(k))))
  }

  // Is the current selection different from what the active preset is defined as?
  // Only sections actually available for this note are compared, so a note with
  // no live data doesn't read as "modified" just for lacking that group.
  const presetDef = useMemo(
    () => (preset === 'full' || preset === 'custom')
      ? null : new Set(presetKeys(preset).filter((k) => allKeys.includes(k))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [preset, allKeys, presetRev])
  const presetDirty = !!presetDef
    && (presetDef.size !== sel.size || [...sel].some((k) => !presetDef.has(k)))
  const savePreset = () => {
    if (preset === 'full' || preset === 'custom') return
    // Merge: keep any keys the definition had that this note can't offer (e.g.
    // live sections on a note with no issue date), so saving from a note without
    // them doesn't quietly strip them from the preset for every other note.
    const unavailable = presetKeys(preset).filter((k) => !allKeys.includes(k))
    savePresetOverride(preset, [...unavailable, ...allKeys.filter((k) => sel.has(k))])
    setPresetRev((r) => r + 1)
    toast.push({ title: t('rep_preset_saved', { name: t(`rep_preset_${preset}`) }), tone: 'accent', icon: 'check' })
  }
  const resetPreset = () => {
    if (preset === 'full' || preset === 'custom') return
    resetPresetOverride(preset)
    setPresetRev((r) => r + 1)
    setSel(new Set(presetKeys(preset).filter((k) => allKeys.includes(k))))
  }

  // Persist the custom selection whenever it changes, so it's there next session.
  useEffect(() => {
    if (preset !== 'custom') return
    try { localStorage.setItem(CUSTOM_LS, JSON.stringify([...sel])) } catch { /* ignore */ }
  }, [sel, preset])

  // Mirror the live selection to the shared store the PDF Studio proof reads, so
  // the preview shows exactly the pages that will be printed (any preset, not
  // just custom).
  useEffect(() => { saveActiveSections([...sel]) }, [sel])

  const generate = async () => {
    setStatus('running'); setError('')
    try {
      const branding = Object.values(brand).some(Boolean) ? brand : null
      // Sync render on purpose: on Cloud Run, CPU is only allocated while a
      // request is in flight, so a background job (the /api/report/start +
      // polling flow) starves and never finishes. The async endpoints still
      // exist for deployments with always-allocated CPU.
      const res = await api.report({
        terms, sections: [...sel], lang, branding,
        n_paths: opts.n_paths, seed: opts.seed, calib_years: opts.calib_years, engine: opts.engine,
        compare_terms: compareOn && variantB ? variantB : null,
        // Stamps the report type on the cover. "custom" has no audience to name,
        // so it goes out untyped rather than labelled "Custom report".
        report_kind: preset === 'custom' ? null : preset,
        // The captured path-explorer selection(s); the backend renders them only
        // when the "Selected path(s)" section (mc_single_wof) is included.
        path_images: pathImages ?? [],
      })
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const filename = filenameFrom(res, 'structured_note_report.pdf')
      const a = document.createElement('a'); a.href = url; a.download = filename
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
      setStatus('done')
      const mb = blob.size / 1048576
      const size = mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(blob.size / 1024))} KB`
      toast.push({ title: t('report_downloaded'), sub: `${filename} · ${size}` })
    } catch (e) { setError(String(e instanceof Error ? e.message : e)); setStatus('error') }
  }

  const none = sel.size === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('report_intro')}</div>
        <button className="btn btn--ghost" style={{ padding: '7px 12px', whiteSpace: 'nowrap', flexShrink: 0 }}
                onClick={() => startTour(reportTour(t))}>
          <Icon name="info" size={14} /> {t('rep_tutorial')}
        </button>
      </div>

      <Panel title={t('report_sections')}>
        <div style={{ marginBottom: 18 }} data-tour="rep-presets">
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 9 }}>{t('rep_preset')}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
            {PRESET_ORDER.map((p) => (
              <button key={p} type="button" className="preset-pill" data-on={preset === p}
                      title={t(`rep_preset_${p}_desc`)} onClick={() => applyPreset(p)}>
                {t(`rep_preset_${p}`)}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 9, lineHeight: 1.5 }}>{t(`rep_preset_${preset}_desc`)}</div>
          {/* Audience presets are the user's own templates: tick the sections you
              want below, then save them INTO the preset. */}
          {presetDef && (presetDirty || isPresetCustomised(preset)) && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              {presetDirty && (
                <button type="button" className="btn" style={{ padding: '5px 11px', fontSize: 12 }} onClick={savePreset}>
                  <Icon name="save" size={13} /> {t('rep_preset_save', { name: t(`rep_preset_${preset}`) })}
                </button>
              )}
              {isPresetCustomised(preset) && (
                <button type="button" className="btn btn--ghost" style={{ padding: '5px 11px', fontSize: 12 }} onClick={resetPreset}>
                  <Icon name="refresh" size={13} /> {t('rep_preset_reset')}
                </button>
              )}
              <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>
                {presetDirty ? t('rep_preset_dirty') : t('rep_preset_customised')}
              </span>
            </div>
          )}
        </div>
        {variantB && (
          <div style={{ marginBottom: 18, padding: '12px 14px', borderRadius: 10,
                        background: 'var(--accent-weak)', border: '1px solid var(--accent)' }}>
            <button onClick={() => setCompareOn((v) => !v)}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: 0, width: '100%' }}>
              <Check on={compareOn} />
              <span style={{ fontSize: 13.5, fontWeight: 700 }}>{t('rep_include_compare')}</span>
            </button>
            <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 6, marginLeft: 28, lineHeight: 1.5 }}>
              {t('rep_compare_hint', { name: variantB.name || t('cmp_note_b') })}
            </div>
          </div>
        )}
        <div data-tour="rep-sections" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: '4px 28px' }}>
          {groups.map((g) => {
            const ks = g.items.map((i) => i[0])
            const onCount = ks.filter((k) => sel.has(k)).length
            return (
              <div key={g.key} style={{ marginBottom: 14 }}>
                <button onClick={() => toggleGroup(g)}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '6px 0', width: '100%' }}>
                  <Check on={onCount === ks.length} indeterminate={onCount > 0 && onCount < ks.length} />
                  <span style={{ fontSize: 13.5, fontWeight: 700 }}>{lab(g.en, g.es)}</span>
                </button>
                {g.items.map(([k, en, es]) => (
                  <button key={k} onClick={() => toggle(k)}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '5px 0 5px 26px', width: '100%' }}>
                    <Check on={sel.has(k)} />
                    <span style={{ fontSize: 13, color: 'var(--text)' }}>{lab(en, es)}</span>
                  </button>
                ))}
              </div>
            )
          })}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 6, lineHeight: 1.5 }}>{t('report_note')}</div>
      </Panel>

      {/* Load the brand config for this report without detouring into the
          Designer (which still owns the full editing surface). */}
      <Panel title={t('rep_brand_config')}>
        <BrandConfigBar studio={studio} compact />
      </Panel>

      {/* Pictures are usually chosen per report, so they live here too — the
          same controls as the Designer, editing the same shared state. */}
      <Panel title={t('rep_images')}>
        <ReportImages studio={studio} terms={terms} />
      </Panel>

      {/* The durable design/identity settings live in the PDF Designer sub-tab. */}
      <Panel pad={0}>
        <button onClick={() => onOpenDesigner?.()}
          style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '14px 16px', color: 'var(--text)', textAlign: 'left' }}>
          <Icon name="chart" size={15} />
          <span style={{ fontSize: 13, fontWeight: 600 }}>{t('rep_open_designer')}</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)', marginLeft: 6 }}>{t('rep_open_designer_hint')}</span>
          <span style={{ marginLeft: 'auto', color: 'var(--text-faint)' }}>›</span>
        </button>
      </Panel>

      <div data-tour="rep-generate" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <button className="btn btn--primary" onClick={generate} disabled={status === 'running' || none} style={{ padding: '12px 22px', fontSize: 14 }}>
          <Icon name={status === 'running' ? 'spinner' : 'chart'} size={16} />
          {status === 'running' ? t('report_generating') : t('report_generate')}
        </button>
        {none && <span style={{ fontSize: 12.5, color: 'var(--amber)' }}>{t('report_select_one')}</span>}
        {status === 'done' && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--green)' }}><Icon name="check" size={15} /> {t('report_downloaded')}</span>}
        {status === 'error' && <span style={{ fontSize: 12.5, color: 'var(--red)' }}><strong>{t('error')}.</strong> {error}</span>}
      </div>
    </div>
  )
}
