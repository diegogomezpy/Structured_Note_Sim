import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { monthsNum } from '../lib/terms'
import { useI18n } from '../i18n/I18nProvider'
import Panel, { LoadingPanel } from './Panel'
import Figure from './Figure'
import Icon from './Icon'
import type { ExplorerData, ExplorerPath } from '../api/types'

type Kind = 'ac' | 'mat' | 'ki' | 'up' | 'par' | 'down'
/* Mercator outcome palette (distinct shades so autocalled vs held read apart):
   autocalled viridian, held-to-maturity secondary viridian, knocked-in claret.
   Participation: above-par viridian, at-par slate, below-par (loss) claret.
   Used for both the chart traces and the DOM legend chips; plotlyTheme lightens
   these in dark mode. */
const KIND_COLOR: Record<Kind, string> = {
  ac: '#15694e', mat: '#3f8a6f', ki: '#9c3b30',
  up: '#15694e', par: '#64748b', down: '#9c3b30',
}

function classify(p: ExplorerPath, isPart: boolean): Kind {
  if (isPart) {
    const r = p.red ?? (p.ki ? 0.99 : 1.01)
    if (r > 1 + 1e-9) return 'up'
    if (r < 1 - 1e-9) return 'down'
    return 'par'
  }
  if (p.ap > 0) return 'ac'
  return p.ki ? 'ki' : 'mat'
}

/** Concatenate a group's paths into one trace, null-separated, so hundreds of
    paths render as a single (WebGL) line series instead of hundreds of traces. */
function group(paths: ExplorerPath[], t: number[], color: string, name: string) {
  const x: (number | null)[] = []
  const y: (number | null)[] = []
  for (const p of paths) {
    // `t` is in years (the engine's unit); the axis is quoted in months.
    for (let i = 0; i < t.length; i++) { x.push(monthsNum(t[i])); y.push(p.wof[i]) }
    x.push(null); y.push(null)
  }
  return { x, y, type: 'scattergl', mode: 'lines', name, line: { color, width: 1 }, opacity: 0.22, hoverinfo: 'skip' }
}

/** Shared worst-of fan: overlaid trajectories coloured by outcome, with outcome
    filter chips, barrier reference lines, and a resample control. Used by both the
    Monte Carlo and the historical-backtest path explorers. */
export function PathFan({
  data, intro, onResample, xLabel, sampledNoun,
}: {
  data: ExplorerData
  intro: string
  onResample: () => void
  xLabel?: string
  sampledNoun?: string
}) {
  const { t } = useI18n()
  const [filter, setFilter] = useState<'all' | Kind>('all')
  const isPart = data.note_type === 'participation'
  const part = data.barriers.participation

  const counts = useMemo(() => {
    const c: Record<Kind, number> = { ac: 0, mat: 0, ki: 0, up: 0, par: 0, down: 0 }
    data.paths.forEach((p) => { c[classify(p, isPart)] += 1 })
    return c
  }, [data, isPart])

  const fig = useMemo(() => {
    const groups: { kind: Kind; label: string }[] = isPart
      ? [{ kind: 'up', label: t('fan_above_par') },
         { kind: 'par', label: t('fan_at_par') },
         { kind: 'down', label: t('fan_below_par') }]
      : [{ kind: 'ac', label: t('autocalled_at') },
         { kind: 'mat', label: t('held_to_mat') },
         { kind: 'ki', label: t('knocked_in') }]
    const traces = groups
      .filter((g) => filter === 'all' || filter === g.kind)
      .map((g) => group(data.paths.filter((p) => classify(p, isPart) === g.kind), data.t, KIND_COLOR[g.kind], g.label))
      .filter((tr) => tr.x.length > 0)

    // A held note's realised stretch sits at negative time, so the axis starts before
    // the simulation does. Its last point IS today's level — the same level every
    // simulated path opens at — so the two halves join exactly.
    const hist = data.realised
    const x0 = monthsNum(hist?.t.length ? hist.t[0] : data.t[0])
    const x1 = monthsNum(data.t[data.t.length - 1])
    const hline = (yv: number | null | undefined, color: string, dash: string) => yv == null ? null : ({
      type: 'line', x0, x1, y0: yv, y1: yv, line: { color, width: 1, dash },
    })
    const vline = (xv: number, color: string, dash: string) => ({
      type: 'line', x0: xv, x1: xv, yref: 'paper', y0: 0, y1: 1,
      line: { color, width: 1, dash },
    })
    const shapes = (isPart
      ? [hline(1, '#94a3b8', 'dot'),
         hline(part?.floor, '#ef4444', 'dash'),
         part?.cap != null ? hline(part.cap, '#94a3b8', 'dash') : null]
      : [hline(1, '#94a3b8', 'dot'),
         hline(data.barriers.knock_in, '#ef4444', 'dash'),
         data.barriers.autocall != null && data.barriers.autocall !== 1
           ? hline(data.barriers.autocall, '#94a3b8', 'dash') : null]
    // Colours are HEX LITERALS FROM plotlyTheme's remap table, never CSS variables:
    // Plotly does not resolve var(--…) and silently falls back, which is how the
    // realised line first rendered alarm-red inside a viridian chart. #2c3e50 maps to
    // the ink token (near-black in light, near-white in dark) and #64748b to mid grey.
    ).concat(hist ? [
      vline(0, '#64748b', 'solid'),                        // today
      ...(hist.settle_t != null && hist.settle_t < -1e-6
        ? [vline(monthsNum(hist.settle_t), '#64748b', 'dot')]  // bought here
        : []),
    // The backtest fan has no realised stretch — its windows are all historical — but
    // it does replicate the purchase gap, so mark where the position started on its
    // own note-relative axis. Everything left of the line belonged to the seller.
    ] : (data.purchase_gap_years
      ? [vline(monthsNum(data.purchase_gap_years), '#64748b', 'dot')]
      : [])).filter(Boolean)

    const markAt = hist ? hist.settle_t : data.purchase_gap_years
    const annos = [
      ...(hist ? [{ x: 0, yref: 'paper', y: 1.02, text: t('fan_today'), showarrow: false,
                    font: { size: 10 }, xanchor: 'center' as const }] : []),
      ...(markAt != null && Math.abs(markAt) > 1e-6
        ? [{ x: monthsNum(markAt), yref: 'paper', y: 1.02, text: t('fan_bought'),
             showarrow: false, font: { size: 10 }, xanchor: 'center' as const }]
        : []),
    ]

    // Drawn last so it sits above the fan — this line is what actually happened, and
    // it should read as fact against the cloud of possibilities.
    if (hist) {
      traces.push({
        x: hist.t.map(monthsNum), y: hist.line, mode: 'lines', type: 'scattergl',
        name: t('fan_realised'), line: { color: '#2c3e50', width: 2.4 },
        hovertemplate: '%{y:.1%}<extra></extra>',
      } as unknown as typeof traces[number])
    }

    return {
      data: traces,
      layout: {
        xaxis: { title: { text: xLabel ?? t('chart_time_years') }, range: [x0, x1], zeroline: false },
        yaxis: { title: { text: isPart ? t('fan_basket_axis') : t('chart_wof') }, tickformat: '.0%', zeroline: false },
        shapes,
        annotations: annos,
        showlegend: true,
        legend: { orientation: 'h', y: 1.06, x: 0 },
        hovermode: 'closest',
      },
    }
  }, [data, filter, t, xLabel, isPart, part])

  const shown = filter === 'all' ? data.paths.length : counts[filter]
  const chips: { id: 'all' | Kind; label: string; n: number; color?: string }[] = isPart
    ? [{ id: 'all', label: t('filter_all'), n: data.paths.length },
       { id: 'up', label: t('fan_above_par'), n: counts.up, color: KIND_COLOR.up },
       { id: 'par', label: t('fan_at_par'), n: counts.par, color: KIND_COLOR.par },
       { id: 'down', label: t('fan_below_par'), n: counts.down, color: KIND_COLOR.down }]
    : [{ id: 'all', label: t('filter_all'), n: data.paths.length },
       { id: 'ac', label: t('autocalled_at'), n: counts.ac, color: KIND_COLOR.ac },
       { id: 'mat', label: t('held_to_mat'), n: counts.mat, color: KIND_COLOR.mat },
       { id: 'ki', label: t('knocked_in'), n: counts.ki, color: KIND_COLOR.ki }]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{intro}</div>

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
        {chips.map((c) => {
          const on = filter === c.id
          return (
            <button key={c.id} onClick={() => setFilter(c.id)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 7, cursor: 'pointer',
                fontFamily: 'inherit', fontSize: 12.5, fontWeight: 500, padding: '6px 12px', borderRadius: 999,
                border: `1px solid ${on ? 'var(--accent)' : 'var(--border-strong)'}`,
                background: on ? 'var(--accent-weak)' : 'transparent',
                color: on ? 'var(--accent-text)' : 'var(--text-muted)',
              }}>
              {c.color && <span style={{ width: 9, height: 9, borderRadius: 3, background: c.color }} />}
              {c.label}
              <span className="mono" style={{ opacity: 0.7 }}>{c.n}</span>
            </button>
          )
        })}
        <button className="btn btn--ghost" style={{ marginLeft: 'auto', padding: '6px 12px' }} onClick={onResample}>
          <Icon name="refresh" size={14} /> {t('explorer_resample')}
        </button>
      </div>

      <Panel pad={14} right={`${t('explorer_showing')} ${shown.toLocaleString()} ${t('explorer_of')} ${data.n_total.toLocaleString()} ${sampledNoun ?? t('explorer_sampled')}`}>
        <div style={{ height: 440 }}><Figure fig={fig} name="worst_of_paths" /></div>
      </Panel>
    </div>
  )
}


/** A representative fraction of the calculated paths (not a flat 400), clamped
    for render performance. */
export function sampleSize(total: number): number {
  return Math.max(400, Math.min(2000, Math.round(total * 0.1)))
}

/** Monte Carlo path explorer — samples worst-of trajectories from a cached run. */
export default function PathExplorer({ runId, total }: { runId: string; total: number }) {
  const { t } = useI18n()
  const [data, setData] = useState<ExplorerData | null>(null)
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading')
  const [seedKey, setSeedKey] = useState(0)

  useEffect(() => {
    let alive = true
    setStatus('loading')
    api.runPaths(runId, sampleSize(total)).then((d) => { if (alive) { setData(d); setStatus('ok') } })
      .catch(() => { if (alive) setStatus('error') })
    return () => { alive = false }
  }, [runId, total, seedKey])

  if (status === 'error') {
    return <Panel pad={40}><div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>{t('explorer_expired')}</div></Panel>
  }
  if (status === 'loading' || !data) return <LoadingPanel />
  return <PathFan data={data} intro={data.note_type === 'participation' ? t('explorer_intro_part') : t('explorer_intro')}
                  onResample={() => setSeedKey((k) => k + 1)} />
}
