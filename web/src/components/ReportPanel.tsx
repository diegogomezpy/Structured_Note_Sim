import { useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Icon from './Icon'
import type { Branding, NoteTerms } from '../api/types'
import type { RunOpts } from './SetupRail'

type Status = 'idle' | 'running' | 'done' | 'error'
type Item = [key: string, en: string, es: string]
type Group = { key: string; en: string; es: string; items: Item[] }

const TREE: Group[] = [
  { key: 'note', en: 'Note details', es: 'Detalle de la nota', items: [
    ['note_terms', 'Note terms', 'Términos'],
    ['obs_schedule', 'Observation schedule', 'Calendario de observaciones'],
    ['issuer', 'Issuer information', 'Información del emisor'],
    ['underlying_breakdown', 'Underlying breakdown', 'Análisis de subyacentes'],
  ] },
  { key: 'mc', en: 'Monte Carlo', es: 'Monte Carlo', items: [
    ['mc_metrics', 'Summary & metrics', 'Resumen y métricas'],
    ['mc_autocall', 'Autocall by period', 'Autocall por período'],
    ['mc_irr', 'IRR distribution', 'Distribución de TIR'],
    ['mc_wof', 'Worst-of fan chart', 'Abanico del peor de'],
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

export default function ReportPanel({ terms, opts }: { terms: NoteTerms; opts: RunOpts }) {
  const { t, lang } = useI18n()
  const hasLive = !!terms.issue_date
  const groups = useMemo(() => TREE.filter((g) => g.key !== 'live' || hasLive), [hasLive])
  const allKeys = useMemo(() => groups.flatMap((g) => g.items.map((i) => i[0])), [groups])

  const [sel, setSel] = useState<Set<string>>(() => new Set(allKeys))
  const [brandOpen, setBrandOpen] = useState(false)
  const [brand, setBrand] = useState<Branding>({})
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState('')
  const logoRef = useRef<HTMLInputElement>(null)

  const lab = (en: string, es: string) => (lang === 'es' ? es : en)
  const toggle = (k: string) => { setSel((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n }); setStatus('idle') }
  const toggleGroup = (g: Group) => {
    const ks = g.items.map((i) => i[0])
    const allOn = ks.every((k) => sel.has(k))
    setSel((p) => { const n = new Set(p); ks.forEach((k) => allOn ? n.delete(k) : n.add(k)); return n })
    setStatus('idle')
  }
  const setBrandField = (k: keyof Branding, v: string) => setBrand((b) => ({ ...b, [k]: v || undefined }))
  const onLogo = (file: File | undefined) => {
    if (!file) return
    const r = new FileReader(); r.onload = () => setBrandField('logo_base64', String(r.result)); r.readAsDataURL(file)
  }

  const generate = async () => {
    setStatus('running'); setError('')
    try {
      const branding = Object.values(brand).some(Boolean) ? brand : null
      const res = await api.report({
        terms, sections: [...sel], lang, branding,
        n_paths: opts.n_paths, seed: opts.seed, calib_years: opts.calib_years, engine: opts.engine,
      })
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = filenameFrom(res, 'structured_note_report.pdf')
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
      setStatus('done')
    } catch (e) { setError(String(e instanceof Error ? e.message : e)); setStatus('error') }
  }

  const none = sel.size === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('report_intro')}</div>

      <Panel title={t('report_sections')}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: '4px 28px' }}>
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

      {/* Branding (collapsible) */}
      <Panel pad={0}>
        <button onClick={() => setBrandOpen((v) => !v)}
          style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 9, background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '14px 16px', color: 'var(--text)' }}>
          <span style={{ transition: 'transform 0.15s', transform: brandOpen ? 'rotate(90deg)' : 'none', color: 'var(--text-faint)' }}>›</span>
          <span style={{ fontSize: 13, fontWeight: 600 }}>{t('rep_branding')}</span>
          <span style={{ fontSize: 11.5, color: 'var(--text-faint)', marginLeft: 8 }}>{t('rep_branding_opt')}</span>
        </button>
        {brandOpen && (
          <div style={{ padding: '0 16px 18px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
            <Field label={t('brand_firm')}><input type="text" value={brand.firm_name ?? ''} onChange={(e) => setBrandField('firm_name', e.target.value)} /></Field>
            <Field label={t('brand_title')}><input type="text" value={brand.report_title ?? ''} onChange={(e) => setBrandField('report_title', e.target.value)} /></Field>
            <Field label={t('brand_footer')}><input type="text" value={brand.footer_note ?? ''} onChange={(e) => setBrandField('footer_note', e.target.value)} /></Field>
            <Field label={t('brand_primary')}>
              <input type="color" value={brand.primary_color ?? '#1a2e4a'} onChange={(e) => setBrandField('primary_color', e.target.value)} style={{ height: 38, padding: 3 }} />
            </Field>
            <Field label={t('brand_accent')}>
              <input type="color" value={brand.accent_color ?? '#2563eb'} onChange={(e) => setBrandField('accent_color', e.target.value)} style={{ height: 38, padding: 3 }} />
            </Field>
            <Field label={t('brand_logo')}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button className="btn" style={{ padding: '7px 12px' }} onClick={() => logoRef.current?.click()}><Icon name="upload" size={13} /> {t('det_upload_logo')}</button>
                {brand.logo_base64 && <img src={brand.logo_base64} alt="logo" style={{ height: 26, borderRadius: 5 }} />}
                {brand.logo_base64 && <button className="btn btn--ghost" style={{ padding: '4px 8px', fontSize: 11.5 }} onClick={() => setBrandField('logo_base64', '')}>{t('det_reset_logo')}</button>}
                <input ref={logoRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => onLogo(e.target.files?.[0])} />
              </div>
            </Field>
          </div>
        )}
      </Panel>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ fontSize: 11.5, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{label}</label>
      {children}
    </div>
  )
}
