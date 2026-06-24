import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Figure from './Figure'
import Icon from './Icon'
import TickerLogo from './TickerLogo'
import { pct, pctSigned, num } from '../lib/format'
import type { InspectResult, NoteTerms } from '../api/types'

type Outcome = 'any' | 'autocalled' | 'maturity' | 'loss'
type KiChoice = 'any' | 'yes' | 'no'

/** Dual-thumb range slider (return band). Two overlaid range inputs; CSS keeps
    only the thumbs interactive (see .range-dual in index.css). */
function RangeSlider({ min, max, step, lo, hi, onChange, fmt }: {
  min: number; max: number; step: number; lo: number; hi: number
  onChange: (lo: number, hi: number) => void; fmt: (v: number) => string
}) {
  const span = max - min || 1
  const pl = ((lo - min) / span) * 100
  const ph = ((hi - min) / span) * 100
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 8 }}>
        <span className="mono" style={{ color: 'var(--text-muted)' }}>{fmt(lo)}</span>
        <span className="mono" style={{ color: 'var(--text-muted)' }}>{fmt(hi)}</span>
      </div>
      <div className="range-dual">
        <div className="range-track" />
        <div className="range-fill" style={{ left: `${pl}%`, right: `${100 - ph}%` }} />
        <input type="range" min={min} max={max} step={step} value={lo}
               onChange={(e) => onChange(Math.min(parseFloat(e.target.value), hi), hi)} />
        <input type="range" min={min} max={max} step={step} value={hi}
               onChange={(e) => onChange(lo, Math.max(parseFloat(e.target.value), lo))} />
      </div>
    </div>
  )
}

function Segmented<T extends string>({ value, options, onChange }: {
  value: T; options: { v: T; label: string }[]; onChange: (v: T) => void
}) {
  return (
    <div style={{ display: 'inline-flex', gap: 4, background: 'var(--surface-2)', borderRadius: 9, padding: 3 }}>
      {options.map((o) => {
        const on = value === o.v
        return (
          <button key={o.v} onClick={() => onChange(o.v)}
            style={{
              fontFamily: 'inherit', fontSize: 12.5, fontWeight: 500, padding: '5px 11px', borderRadius: 7,
              border: 'none', cursor: 'pointer',
              background: on ? 'var(--surface)' : 'transparent',
              color: on ? 'var(--text)' : 'var(--text-muted)',
              boxShadow: on ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
            }}>{o.label}</button>
        )
      })}
    </div>
  )
}

function PeriodChips({ n, selected, onToggle }: { n: number; selected: number[]; onToggle: (p: number) => void }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {Array.from({ length: n }, (_, i) => i + 1).map((p) => {
        const on = selected.includes(p)
        return (
          <button key={p} onClick={() => onToggle(p)}
            style={{
              fontFamily: 'inherit', fontSize: 12, fontWeight: 500, padding: '4px 9px', borderRadius: 7, cursor: 'pointer',
              border: `1px solid ${on ? 'var(--accent)' : 'var(--border-strong)'}`,
              background: on ? 'var(--accent-weak)' : 'transparent',
              color: on ? 'var(--accent-text)' : 'var(--text-muted)',
            }}>P{p}</button>
        )
      })}
    </div>
  )
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8 }}>{label}</div>
      {children}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="card" style={{ padding: '12px 14px' }}>
      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6 }}>{label}</div>
      <div className="mono" style={{ fontSize: 20, fontWeight: 600, lineHeight: 1 }}>{value}</div>
    </div>
  )
}

function InspectorPanel({ runId, terms, label, onRemove }: {
  runId: string; terms: NoteTerms; label: string; onRemove?: () => void
}) {
  const { t, lang } = useI18n()
  const nameToSym = useMemo(() => {
    const m: Record<string, string> = {}
    for (const [sym, name] of Object.entries(terms.tickers ?? {})) m[name] = sym
    return m
  }, [terms])

  const [title, setTitle] = useState('')
  const [debTitle, setDebTitle] = useState('')
  const [outcome, setOutcome] = useState<Outcome>('any')
  const [acPeriods, setAcPeriods] = useState<number[]>([])
  const [ki, setKi] = useState<KiChoice>('any')
  const [couponPeriods, setCouponPeriods] = useState<number[]>([])
  const [bounds, setBounds] = useState<[number, number] | null>(null)
  const [band, setBand] = useState<[number, number] | null>(null)
  const [position, setPosition] = useState(0)
  const [data, setData] = useState<InspectResult | null>(null)
  const [filtersOpen, setFiltersOpen] = useState(false)

  const nObs = data?.n_obs ?? 0
  // Debounce the title so typing doesn't refetch on every keystroke.
  useEffect(() => { const id = setTimeout(() => setDebTitle(title), 500); return () => clearTimeout(id) }, [title])

  const filterKey = JSON.stringify({ outcome, acPeriods, ki, couponPeriods, band, atBounds: !bounds })

  // Reset to the first match whenever the filter query changes.
  useEffect(() => { setPosition(0) /* eslint-disable-next-line */ }, [filterKey])

  useEffect(() => {
    let alive = true
    const lo = band && bounds && band[0] > bounds[0] ? band[0] : null
    const hi = band && bounds && band[1] < bounds[1] ? band[1] : null
    api.inspectRun(runId, {
      filters: {
        outcome, ac_periods: outcome === 'autocalled' ? acPeriods : [],
        ki_choice: ki, ret_lo: lo, ret_hi: hi, coupon_periods: couponPeriods,
      },
      position, title: debTitle || null, lang,
    }).then((d) => {
      if (!alive) return
      if (bounds == null && d.ret_range) { setBounds(d.ret_range); setBand(d.ret_range) }
      setData(d)
    }).catch(() => {})
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, filterKey, position, debTitle, lang])

  const M = data?.n_matched ?? 0
  const o = data?.outcome
  const outcomeLine = !o ? '' :
    o.autocall_q > 0 ? t('insp_autocalled', { q: o.autocall_q, t: num(o.call_time, 2) })
    : o.knock_in ? t('insp_mat_ki', { wof: pct(o.worst_final, 1) })
    : t('insp_mat_ok', { wof: pct(o.worst_final, 1) })

  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{t('insp_panel_label', { label })}</div>
        {onRemove && (
          <button className="btn btn--ghost" style={{ padding: '4px 8px' }} onClick={onRemove}><Icon name="x" size={14} /></button>
        )}
      </div>

      <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('insp_panel_name')}</label>
      <input type="text" value={title} placeholder={t('insp_panel_name_ph')} onChange={(e) => setTitle(e.target.value)} style={{ marginBottom: 14 }} />

      {/* Filters (collapsible) */}
      <div style={{ border: '1px solid var(--border)', borderRadius: 10, marginBottom: 14 }}>
        <button onClick={() => setFiltersOpen((v) => !v)}
          style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '11px 14px', color: 'var(--text)' }}>
          <span style={{ transition: 'transform 0.15s', transform: filtersOpen ? 'rotate(90deg)' : 'none', color: 'var(--text-faint)' }}>›</span>
          <Icon name="chart" size={14} />
          <span style={{ fontSize: 12.5, fontWeight: 600 }}>{t('insp_filters')}</span>
        </button>
        {filtersOpen && (
          <div style={{ padding: '4px 14px 16px' }}>
            <FilterRow label={t('insp_outcome')}>
              <Segmented value={outcome} onChange={setOutcome} options={[
                { v: 'any', label: t('insp_oc_any') }, { v: 'autocalled', label: t('insp_oc_autocalled') },
                { v: 'maturity', label: t('insp_oc_maturity') }, { v: 'loss', label: t('insp_oc_loss') },
              ]} />
              {outcome === 'autocalled' && nObs > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 6 }}>{t('insp_ac_periods')}</div>
                  <PeriodChips n={nObs} selected={acPeriods}
                    onToggle={(p) => setAcPeriods((s) => s.includes(p) ? s.filter((x) => x !== p) : [...s, p])} />
                </div>
              )}
            </FilterRow>
            <FilterRow label={t('insp_ki')}>
              <Segmented value={ki} onChange={setKi} options={[
                { v: 'any', label: t('insp_ki_any') }, { v: 'yes', label: t('insp_ki_yes') }, { v: 'no', label: t('insp_ki_no') },
              ]} />
            </FilterRow>
            {bounds && band && (
              <FilterRow label={t('insp_ret')}>
                <RangeSlider min={bounds[0]} max={bounds[1]} step={0.005} lo={band[0]} hi={band[1]}
                  onChange={(lo, hi) => setBand([lo, hi])} fmt={(v) => pctSigned(v, 1)} />
              </FilterRow>
            )}
            {data?.coupon_available && nObs > 0 && (
              <FilterRow label={t('insp_coupon')}>
                <PeriodChips n={nObs} selected={couponPeriods}
                  onToggle={(p) => setCouponPeriods((s) => s.includes(p) ? s.filter((x) => x !== p) : [...s, p])} />
              </FilterRow>
            )}
          </div>
        )}
      </div>

      {/* Match nav */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <button className="btn" style={{ padding: '6px 12px' }} onClick={() => api.inspectRun(runId, { filters: buildFilters(), randomize: true, title: debTitle || null, lang }).then(setData)}>
          <Icon name="refresh" size={13} /> {t('insp_random')}
        </button>
        <button className="btn" style={{ padding: '6px 12px' }} disabled={(data?.position ?? 0) <= 0} onClick={() => setPosition((p) => Math.max(0, p - 1))}>{t('insp_prev')}</button>
        <button className="btn" style={{ padding: '6px 12px' }} disabled={(data?.position ?? 0) >= M - 1} onClick={() => setPosition((p) => p + 1)}>{t('insp_next')}</button>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {M > 0 && data?.path_index != null
            ? t('insp_match_caption', { k: (data.position ?? 0) + 1, m: M, n: data.path_index })
            : t('insp_match_count', { m: M, total: data?.n_total ?? 0 })}
        </span>
      </div>

      {M === 0 ? (
        <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>{t('insp_no_matches')}</div>
      ) : data?.figure ? (
        <>
          <div style={{ height: 360 }}><Figure fig={data.figure} /></div>
          {outcomeLine && <div style={{ fontSize: 13, color: 'var(--text-muted)', margin: '8px 0 12px' }}>{outcomeLine}</div>}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 12 }}>
            <Metric label={t('insp_m_principal')} value={pct(data.metrics?.principal, 2)} />
            <Metric label={t('insp_m_coupons')} value={pct(data.metrics?.coupons, 2)} />
            <Metric label={t('insp_m_irr')} value={pct(data.metrics?.irr, 2)} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
            {data.assets?.map((a) => {
              const d = a.final != null ? a.final - 1 : null
              return (
                <div key={a.name} className="card" style={{ padding: '10px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
                    <TickerLogo symbol={nameToSym[a.name] ?? a.name} name={a.name} size={16} />
                    <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>
                  </div>
                  <div className="mono" style={{ fontSize: 16, fontWeight: 600 }}>{pct(a.final, 1)}</div>
                  <div className="mono" style={{ fontSize: 11, marginTop: 3, color: (d ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{pctSigned(d, 1)}</div>
                </div>
              )
            })}
          </div>
        </>
      ) : null}
    </Panel>
  )

  function buildFilters() {
    const lo = band && bounds && band[0] > bounds[0] ? band[0] : null
    const hi = band && bounds && band[1] < bounds[1] ? band[1] : null
    return { outcome, ac_periods: outcome === 'autocalled' ? acPeriods : [], ki_choice: ki, ret_lo: lo, ret_hi: hi, coupon_periods: couponPeriods }
  }
}

/** Single-path inspector — 1 to 3 comparison panels, each filtering the run's
    paths and stepping through the matches. Sits below the worst-of fan. */
export default function PathInspector({ runId, terms }: { runId: string; terms: NoteTerms }) {
  const { t } = useI18n()
  const [ids, setIds] = useState<number[]>([0])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{t('inspect_heading')}</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('inspect_intro')}</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: ids.length > 1 ? 'repeat(auto-fit, minmax(440px, 1fr))' : '1fr', gap: 16 }}>
        {ids.map((id, i) => (
          <InspectorPanel key={id} runId={runId} terms={terms} label={String.fromCharCode(65 + i)}
            onRemove={i === 0 ? undefined : () => setIds((s) => s.filter((x) => x !== id))} />
        ))}
      </div>
      {ids.length < 3 && (
        <button className="btn" style={{ alignSelf: 'flex-start', padding: '9px 16px' }}
          onClick={() => setIds((s) => [...s, (Math.max(...s) + 1)])}>
          <Icon name="plus" size={15} /> {t('insp_add_panel')}
        </button>
      )}
    </div>
  )
}
