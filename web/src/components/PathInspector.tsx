import { useCallback, useEffect, useMemo, useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Figure from './Figure'
import Icon from './Icon'
import TickerLogo from './TickerLogo'
import { pct, pctSigned, num } from '../lib/format'
import { figureToReportPng } from '../lib/figurePng'
import type { InspectFilters, InspectResult, NoteTerms, PathData } from '../api/types'

/** One captured path-explorer chart, ready to embed in the PDF report. */
export interface PathImage { title: string; png: string }

type Outcome = 'any' | 'autocalled' | 'maturity' | 'loss' | 'part_gain' | 'part_par' | 'part_loss'
type KiChoice = 'any' | 'yes' | 'no'

/** A panel fetches its detail through this — MC hits /runs/{id}/inspect, the
    backtest hits /backtest/inspect, both returning the same InspectResult. */
export type InspectFetcher = (body: {
  filters?: InspectFilters; position?: number; randomize?: boolean; lang?: string
}) => Promise<InspectResult>

// Underlyings recede to muted, non-blue tones so the worst-of (brand accent) reads
// as the hero rather than competing.
const ASSET_COLORS = ['#64748b', '#0d9488', '#a855f7', '#d97706', '#0891b2']
const WOF_COLOR = '#2563eb'
const MARKER_STYLE: Record<string, { symbol: string; color: string; size: number }> = {
  call:     { symbol: 'diamond', color: '#2563eb', size: 11 },
  coupon:   { symbol: 'circle', color: '#16a34a', size: 9 },
  missed:   { symbol: 'circle-open', color: '#d97706', size: 9 },
  redeem:   { symbol: 'star', color: '#16a34a', size: 13 },
  knock_in: { symbol: 'x', color: '#dc2626', size: 11 },
  // Participation kinds
  part_hold:   { symbol: 'circle', color: '#94a3b8', size: 6 },
  part_redeem: { symbol: 'star', color: '#16a34a', size: 13 },
  part_gain:   { symbol: 'triangle-up', color: '#16a34a', size: 11 },
  part_loss:   { symbol: 'triangle-down', color: '#dc2626', size: 11 },
  part_flat:   { symbol: 'circle', color: '#94a3b8', size: 8 },
}
// 'call_coupon' (autocall that also paid a coupon) shares the autocall marker.
const normKind = (k: string) => (k === 'call_coupon' ? 'call' : k)
const KIND_ORDER = ['coupon', 'missed', 'call', 'redeem', 'knock_in',
                    'part_hold', 'part_gain', 'part_flat', 'part_loss', 'part_redeem']
// Vertical spacing (perf units) between the dots when a memory release pays
// several coupons at once — drawn as a small stack.
const STACK_DY = 0.03

interface PathLabels {
  x: string; y: string; wof: string
  par: string; ki: string; ac: string
  floor: string; cap: string; strike: string
  ev: Record<string, string>
}

/** Renormalise a per-day series so each cliquet reset period restarts at 100%.
    A cliquet's strike resets every period, so its "base" for measuring the move
    changes at each reset — this divides each period's segment by the (cumulative)
    level at that period's start, giving the per-period move the payoff actually
    uses. `resetXs` are the reset x-positions (ascending). */
function renormPerPeriod(tArr: number[], yArr: number[], resetXs: number[]): number[] {
  if (!resetXs.length || !yArr.length) return yArr
  const valAt = (x: number) => {
    let bi = 0, bd = Infinity
    for (let k = 0; k < tArr.length; k++) { const d = Math.abs(tArr[k] - x); if (d < bd) { bd = d; bi = k } }
    return yArr[bi]
  }
  const refAt = resetXs.map(valAt)
  const base = yArr[0] || 1
  return yArr.map((v, i) => {
    let j = 0
    while (j < resetXs.length && resetXs[j] < tArr[i] - 1e-9) j++
    const ref = j === 0 ? base : (refAt[j - 1] || base)
    return ref ? v / ref : v
  })
}

/** Build the single-path figure client-side, in the app's chart aesthetic.
    Every series — the underlyings, the worst-of, the par / knock-in / autocall
    reference levels, and each event-marker type — is a named trace so the
    horizontal top legend fully explains the chart. When `renorm` (cliquet
    per-period view) the basket, underlyings and reset markers are renormalised so
    every reset period restarts at 100%. */
function buildPathFig(path: PathData, labels: PathLabels, renorm = false) {
  // Reset x-positions of a cliquet = its per-period participation markers.
  const resetXs = renorm
    ? [...new Set(path.markers.filter((m) => m.kind.startsWith('part_')).map((m) => m.x))].sort((a, b) => a - b)
    : []
  const on = renorm && resetXs.length > 0
  const rn = (y: number[]) => (on ? renormPerPeriod(path.t, y, resetXs) : y)
  // In the per-period view each reset restarts the basis at 100%, so a single
  // continuous line would draw a vertical cliff from a high period-end straight down
  // to the next period's 100%. Break the line at each reset (except the last) so the
  // sawtooth reads as separate per-period arcs instead of spurious crashes. The reset
  // vertex sits exactly on a sampled column (the engine forces obs steps onto the grid).
  const breakIdx = new Set<number>()
  if (on) {
    for (let k = 0; k < resetXs.length - 1; k++) {
      const idx = path.t.findIndex((x) => Math.abs(x - resetXs[k]) < 1e-6)
      if (idx >= 0) breakIdx.add(idx)
    }
  }
  // Insert a gap (null y) right after each reset vertex so Plotly lifts the pen there.
  const withGaps = (y: (number | null)[]): { x: number[]; y: (number | null)[] } => {
    if (!breakIdx.size) return { x: path.t, y }
    const X: number[] = [], Y: (number | null)[] = []
    for (let i = 0; i < y.length; i++) {
      X.push(path.t[i]); Y.push(y[i])
      if (breakIdx.has(i)) { X.push(path.t[i]); Y.push(null) }
    }
    return { x: X, y: Y }
  }
  // Per-period reference divisor for a marker sitting at x (its period's start level).
  const wofRefAt = resetXs.map((rx) => {
    let bi = 0, bd = Infinity
    for (let k = 0; k < path.t.length; k++) { const d = Math.abs(path.t[k] - rx); if (d < bd) { bd = d; bi = k } }
    return path.wof[bi]
  })
  const base = path.wof[0] || 1
  const refForX = (x: number) => {
    let j = 0
    while (j < resetXs.length && resetXs[j] < x - 1e-9) j++
    return j === 0 ? base : (wofRefAt[j - 1] || base)
  }
  const mY = (m: { x: number; y: number }) => (on ? m.y / refForX(m.x) : m.y)

  const traces: any[] = []
  path.series.forEach((s, i) => {
    const g = withGaps(rn(s.perf))
    traces.push({
      x: g.x, y: g.y, mode: 'lines', name: s.name, type: 'scatter', connectgaps: false,
      line: { color: ASSET_COLORS[i % ASSET_COLORS.length], width: 1, dash: 'dot' }, opacity: 0.5,
    })
  })
  const gw = withGaps(rn(path.wof))
  traces.push({ x: gw.x, y: gw.y, mode: 'lines', name: labels.wof, type: 'scatter', connectgaps: false, line: { color: WOF_COLOR, width: 2 } })

  // Reference levels as named, non-hovering line traces (so they appear in the legend).
  const x0 = 0, x1 = path.x_max
  const level = (y: number, name: string, color: string, dash: string) => ({
    x: [x0, x1], y: [y, y], mode: 'lines', type: 'scatter', name, hoverinfo: 'skip',
    line: { color, width: 1, dash },
  })
  traces.push(level(1, labels.par, '#94a3b8', 'dot'))
  const part = path.barriers.participation
  if (part) {
    // Participation payoff reference levels — protection floor, cap, strike (par is
    // always drawn above). Knock-in / autocall lines don't apply.
    if (part.floor != null) traces.push(level(part.floor, labels.floor, '#dc2626', 'dash'))
    if (part.cap != null) traces.push(level(part.cap, labels.cap, '#94a3b8', 'dash'))
    if (part.strike != null && part.strike !== 1) traces.push(level(part.strike, labels.strike, '#94a3b8', 'dot'))
  } else {
    if (path.barriers.knock_in != null) traces.push(level(path.barriers.knock_in, labels.ki, '#dc2626', 'dash'))
    const sched = path.barriers.autocall_schedule
    if (sched) {
      const s = sched.filter(([step]) => step <= x1)
      if (s.length) traces.push({
        x: [0, ...s.map((p) => p[0])], y: [s[0][1], ...s.map((p) => p[1])],
        mode: 'lines', type: 'scatter', name: labels.ac, hoverinfo: 'skip',
        line: { color: '#94a3b8', dash: 'dash', width: 1.3, shape: 'hv' },
      })
    } else if (path.barriers.autocall != null && path.barriers.autocall !== 1) {
      traces.push(level(path.barriers.autocall, labels.ac, '#94a3b8', 'dash'))
    }
  }

  // Event markers — one named trace per kind present, ordered for a tidy legend.
  // A memory payout (m.n > 1) is drawn as a small vertical stack of dots so you
  // can see how many accrued coupons were released at that observation.
  const byKind: Record<string, typeof path.markers> = {}
  path.markers.forEach((m) => { (byKind[normKind(m.kind)] ||= []).push(m) })
  Object.keys(byKind).sort((a, b) => KIND_ORDER.indexOf(a) - KIND_ORDER.indexOf(b)).forEach((kind) => {
    const ms = byKind[kind]
    const st = MARKER_STYLE[kind] ?? MARKER_STYLE.coupon
    const xs: number[] = [], ys: number[] = [], text: string[] = []
    ms.forEach((m) => {
      const stacks = Math.max(1, m.n ?? 1)
      const y0 = mY(m)
      for (let j = 0; j < stacks; j++) { xs.push(m.x); ys.push(y0 + j * STACK_DY); text.push(m.text) }
    })
    traces.push({
      x: xs, y: ys, text, mode: 'markers', type: 'scatter', name: labels.ev[kind] ?? kind,
      marker: { symbol: st.symbol, color: st.color, size: st.size, line: { color: '#fff', width: 1.5 } },
      hovertemplate: '%{text}<extra></extra>',
    })
  })

  const pad = Math.max(1, x1 * 0.015)
  // Per-period view: a faint dashed vertical divider at each reset makes the period
  // boundaries explicit (they line up with the locked-in-gain markers and the line
  // breaks). yref 'paper' so each spans the full plot height regardless of y-range.
  const shapes = on ? resetXs.map((rx) => ({
    type: 'line', xref: 'x', yref: 'paper', x0: rx, x1: rx, y0: 0, y1: 1,
    line: { color: '#94a3b8', width: 1, dash: 'dot' }, layer: 'below',
  })) : []
  return {
    data: traces,
    layout: {
      xaxis: { title: { text: labels.x }, range: [x0 - pad, x1 + pad], zeroline: false },
      yaxis: { title: { text: labels.y }, tickformat: '.0%', zeroline: false },
      shapes,
      showlegend: true, hovermode: 'closest',
      legend: { orientation: 'h', y: 1.14, x: 0, font: { size: 11 }, itemwidth: 30 },
      margin: { l: 58, r: 26, t: 50, b: 46 },
    },
  }
}

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

function InspectorPanel({ fetcher, terms, label, onRemove, panelId, reportImage }: {
  fetcher: InspectFetcher; terms: NoteTerms; label: string; onRemove?: () => void
  panelId?: number; reportImage?: (id: number, img: PathImage | null) => void
}) {
  const { t, lang } = useI18n()
  const nameToSym = useMemo(() => {
    const m: Record<string, string> = {}
    for (const [sym, name] of Object.entries(terms.tickers ?? {})) m[name] = sym
    return m
  }, [terms])

  const [title, setTitle] = useState('')
  const [outcome, setOutcome] = useState<Outcome>('any')
  const [acPeriods, setAcPeriods] = useState<number[]>([])
  const [ki, setKi] = useState<KiChoice>('any')
  const [couponPeriods, setCouponPeriods] = useState<number[]>([])
  const [bounds, setBounds] = useState<[number, number] | null>(null)
  const [band, setBand] = useState<[number, number] | null>(null)
  const [position, setPosition] = useState(0)
  const [data, setData] = useState<InspectResult | null>(null)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [renorm, setRenorm] = useState(false)   // cliquet: per-period renormalised view

  const nObs = data?.n_obs ?? 0
  const filterKey = JSON.stringify({ outcome, acPeriods, ki, couponPeriods, band, atBounds: !bounds })

  const filters = (): InspectFilters => {
    const lo = band && bounds && band[0] > bounds[0] ? band[0] : null
    const hi = band && bounds && band[1] < bounds[1] ? band[1] : null
    return { outcome, ac_periods: outcome === 'autocalled' ? acPeriods : [], ki_choice: ki, ret_lo: lo, ret_hi: hi, coupon_periods: couponPeriods }
  }

  // Reset to the first match whenever the filter query changes.
  useEffect(() => { setPosition(0) /* eslint-disable-next-line */ }, [filterKey])

  useEffect(() => {
    let alive = true
    fetcher({ filters: filters(), position, lang }).then((d) => {
      if (!alive) return
      if (bounds == null && d.ret_range) { setBounds(d.ret_range); setBand(d.ret_range) }
      setData(d)
    }).catch(() => {})
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetcher, filterKey, position, lang])

  const M = data?.n_matched ?? 0
  const isPart = data?.note_type === 'participation'
  const periodic = data?.participation_periodic ?? false
  const o = data?.outcome
  const outcomeLine = !o ? '' :
    isPart
      ? (periodic
          ? t('insp_part_cliquet', { r: pct(o.redemption, 1), inc: pctSigned((data?.metrics?.coupons) ?? 0, 2) })
          : (o.is_loss
              ? t('insp_part_loss', { r: pct(o.redemption, 1), b: pct(o.final_basket, 1) })
              : t('insp_part_ok', { r: pct(o.redemption, 1), b: pct(o.final_basket, 1) })))
    // `autocall_q` indexes the PRICED WINDOW, so a held run that opens at P5 reports
    // its first observation as 1. Every display layer adds period_offset (see the
    // indexing contract in CLAUDE.md) — this line did not, and printed the window
    // index as if it were a term-sheet period: "Autocalled at P3" for a call at P7.
    : o.autocall_q > 0 ? t('insp_autocalled', { q: o.autocall_q + (data?.period_offset ?? 0),
                                                t: num((o.call_time ?? 0) * 12, 1) })
    : o.knock_in ? t('insp_mat_ki', { wof: pct(o.worst_final, 1) })
    : t('insp_mat_ok', { wof: pct(o.worst_final, 1) })

  const fig = useMemo(() => data?.path
    ? buildPathFig(data.path, {
        x: isPart ? t('insp_time_step') : t('insp_time_step'),
        y: isPart ? t('pp_y_axis') : t('chart_wof'),
        wof: isPart ? t('insp_basket_name') : t('insp_wof_name'),
        par: t('insp_lvl_par'), ki: t('insp_lvl_ki'), ac: t('insp_lvl_autocall'),
        floor: t('insp_lvl_floor'), cap: t('insp_lvl_cap'), strike: t('insp_lvl_strike'),
        ev: { coupon: t('insp_ev_coupon'), missed: t('insp_ev_missed'), call: t('insp_ev_call'),
              redeem: t('insp_ev_redeem'), knock_in: t('insp_ev_knock_in'),
              part_hold: t('insp_ev_basket'), part_redeem: t('insp_ev_redeem'),
              part_gain: t('insp_ev_lock_gain'), part_loss: t('insp_ev_lock_loss'), part_flat: t('insp_ev_flat') },
      }, isPart && periodic && renorm)
    : null, [data, t, isPart, periodic, renorm])

  // Capture the current chart as a report-styled PNG and hand it to the parent so
  // the exact path the user is viewing (in whatever view — cumulative / per-period)
  // can be embedded in the PDF's Path Explorer section. Re-captures on every new
  // path / filter / view change.
  useEffect(() => {
    if (!reportImage || panelId == null) return
    if (!fig) { reportImage(panelId, null); return }
    let alive = true
    const cap = title.trim() || (data?.path_index != null
      ? `${isPart ? t('insp_basket_name') : t('insp_wof_name')} · #${data.path_index}`
      : label)
    figureToReportPng(fig).then((png) => { if (alive && png) reportImage(panelId, { title: cap, png }) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fig, title, panelId, reportImage, data?.path_index])
  // Drop this panel's image when it unmounts (e.g. a comparison panel removed).
  useEffect(() => () => { if (reportImage && panelId != null) reportImage(panelId, null) },
            [reportImage, panelId])

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
            <FilterRow label={isPart ? t('insp_outcome_part') : t('insp_outcome')}>
              {isPart ? (
                <Segmented value={outcome} onChange={setOutcome} options={[
                  { v: 'any', label: t('insp_oc_any') }, { v: 'part_gain', label: t('insp_oc_gain') },
                  { v: 'part_par', label: t('insp_oc_par') }, { v: 'part_loss', label: t('insp_oc_below_par') },
                ]} />
              ) : (<>
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
              </>)}
            </FilterRow>
            {!isPart && (
              <FilterRow label={t('insp_ki')}>
                <Segmented value={ki} onChange={setKi} options={[
                  { v: 'any', label: t('insp_ki_any') }, { v: 'yes', label: t('insp_ki_yes') }, { v: 'no', label: t('insp_ki_no') },
                ]} />
              </FilterRow>
            )}
            {bounds && band && (
              <FilterRow label={isPart ? t('insp_ret_part') : t('insp_ret')}>
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
        <button className="btn" style={{ padding: '6px 12px' }} onClick={() => fetcher({ filters: filters(), randomize: true, lang }).then(setData).catch(() => {})}>
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
      ) : fig ? (
        <>
          {title && <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 6 }}>{title}</div>}
          {/* Cliquet: toggle the cumulative basket vs. each reset period renormalised
              to 100% (the per-period basis the payoff actually resets to). */}
          {isPart && periodic && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
              <Segmented value={renorm ? 'period' : 'cum'} onChange={(v) => setRenorm(v === 'period')} options={[
                { v: 'cum', label: t('insp_view_cumulative') },
                { v: 'period', label: t('insp_view_perperiod') },
              ]} />
            </div>
          )}
          {/* Key by the loaded path so the draw-in animation replays on every new
              path (random / next / prev), not just on first mount. */}
          <div style={{ height: 360 }}>
            <Figure key={data?.path_index ?? data?.position ?? 0} fig={fig} name="path_inspector" />
          </div>
          {outcomeLine && <div style={{ fontSize: 13, color: 'var(--text-muted)', margin: '8px 0 12px' }}>{outcomeLine}</div>}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 12 }}>
            {isPart ? (<>
              <Metric label={t('insp_m_redemption')} value={pct(data?.metrics?.principal, 2)} />
              <Metric label={periodic ? t('insp_m_income') : t('insp_m_gain')}
                      value={periodic ? pctSigned(data?.metrics?.coupons, 2) : pctSigned(data?.metrics?.total_return, 2)} />
              <Metric label={t('insp_m_irr')} value={pct(data?.metrics?.irr, 2)} />
            </>) : (<>
              <Metric label={t('insp_m_principal')} value={pct(data?.metrics?.principal, 2)} />
              <Metric label={t('insp_m_coupons')} value={pct(data?.metrics?.coupons, 2)} />
              <Metric label={t('insp_m_irr')} value={pct(data?.metrics?.irr, 2)} />
            </>)}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
            {data?.assets?.map((a) => {
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
}

/** Single-path inspector — 1 to 3 comparison panels, each filtering the run's
    paths and stepping through the matches. Sits below the worst-of fan; the
    `fetcher` decides whether it inspects MC paths or backtest issues. */
export default function PathInspector({ fetcher, terms, onImages }: {
  fetcher: InspectFetcher; terms: NoteTerms
  onImages?: (imgs: PathImage[]) => void   // captured panel charts, for the PDF report
}) {
  const { t } = useI18n()
  const [ids, setIds] = useState<number[]>([0])
  const [imgs, setImgs] = useState<Record<number, PathImage>>({})

  // Stable collector each panel calls with its current captured chart (or null).
  const reportImage = useCallback((id: number, img: PathImage | null) => {
    setImgs((m) => {
      if (!img) { if (!(id in m)) return m; const n = { ...m }; delete n[id]; return n }
      return { ...m, [id]: img }
    })
  }, [])
  // Emit the panels' images to the parent in panel order whenever they change.
  useEffect(() => {
    onImages?.(ids.map((id) => imgs[id]).filter(Boolean) as PathImage[])
  }, [imgs, ids, onImages])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{t('inspect_heading')}</div>
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('inspect_intro')}</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: ids.length > 1 ? 'repeat(auto-fit, minmax(440px, 1fr))' : '1fr', gap: 16 }}>
        {ids.map((id, i) => (
          <InspectorPanel key={id} fetcher={fetcher} terms={terms} label={String.fromCharCode(65 + i)}
            panelId={id} reportImage={reportImage}
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
