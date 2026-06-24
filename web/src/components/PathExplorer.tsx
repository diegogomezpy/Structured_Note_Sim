import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Figure from './Figure'
import Icon from './Icon'
import type { ExplorerData, ExplorerPath } from '../api/types'

type Kind = 'ac' | 'mat' | 'ki'
const KIND_COLOR: Record<Kind, string> = { ac: '#3b82f6', mat: '#22c55e', ki: '#ef4444' }

function classify(p: ExplorerPath): Kind {
  if (p.ap > 0) return 'ac'
  return p.ki ? 'ki' : 'mat'
}

/** Concatenate a group's paths into one trace, null-separated, so hundreds of
    paths render as a single (WebGL) line series instead of hundreds of traces. */
function group(paths: ExplorerPath[], t: number[], color: string, name: string) {
  const x: (number | null)[] = []
  const y: (number | null)[] = []
  for (const p of paths) {
    for (let i = 0; i < t.length; i++) { x.push(t[i]); y.push(p.wof[i]) }
    x.push(null); y.push(null)
  }
  return { x, y, type: 'scattergl', mode: 'lines', name, line: { color, width: 1 }, opacity: 0.22, hoverinfo: 'skip' }
}

export default function PathExplorer({ runId }: { runId: string }) {
  const { t } = useI18n()
  const [data, setData] = useState<ExplorerData | null>(null)
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading')
  const [seedKey, setSeedKey] = useState(0)
  const [filter, setFilter] = useState<'all' | Kind>('all')

  useEffect(() => {
    let alive = true
    setStatus('loading')
    api.runPaths(runId).then((d) => { if (alive) { setData(d); setStatus('ok') } })
      .catch(() => { if (alive) setStatus('error') })
    return () => { alive = false }
  }, [runId, seedKey])

  const counts = useMemo(() => {
    const c = { ac: 0, mat: 0, ki: 0 }
    data?.paths.forEach((p) => { c[classify(p)] += 1 })
    return c
  }, [data])

  const fig = useMemo(() => {
    if (!data) return null
    const groups: { kind: Kind; label: string }[] = [
      { kind: 'ac', label: t('autocalled_at') },
      { kind: 'mat', label: t('held_to_mat') },
      { kind: 'ki', label: t('knocked_in') },
    ]
    const traces = groups
      .filter((g) => filter === 'all' || filter === g.kind)
      .map((g) => group(data.paths.filter((p) => classify(p) === g.kind), data.t, KIND_COLOR[g.kind], g.label))
      .filter((tr) => tr.x.length > 0)

    const x0 = data.t[0], x1 = data.t[data.t.length - 1]
    const hline = (yv: number | null, color: string, dash: string) => yv == null ? null : ({
      type: 'line', x0, x1, y0: yv, y1: yv, line: { color, width: 1, dash },
    })
    const shapes = [
      hline(1, '#94a3b8', 'dot'),
      hline(data.barriers.knock_in, '#ef4444', 'dash'),
      data.barriers.autocall != null && data.barriers.autocall !== 1
        ? hline(data.barriers.autocall, '#94a3b8', 'dash') : null,
    ].filter(Boolean)

    return {
      data: traces,
      layout: {
        xaxis: { title: { text: t('chart_time_years') }, range: [x0, x1], zeroline: false },
        yaxis: { title: { text: t('chart_wof') }, tickformat: '.0%', zeroline: false },
        shapes,
        showlegend: true,
        legend: { orientation: 'h', y: 1.06, x: 0 },
        hovermode: 'closest',
      },
    }
  }, [data, filter, t])

  if (status === 'error') {
    return <Panel pad={40}><div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>{t('explorer_expired')}</div></Panel>
  }
  if (status === 'loading' || !data || !fig) {
    return <Panel pad={40}><div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 14 }}><Icon name="spinner" size={18} /> {t('loading')}</div></Panel>
  }

  const shown = filter === 'all' ? data.paths.length : counts[filter]
  const chips: { id: 'all' | Kind; label: string; n: number; color?: string }[] = [
    { id: 'all', label: t('filter_all'), n: data.paths.length },
    { id: 'ac', label: t('autocalled_at'), n: counts.ac, color: KIND_COLOR.ac },
    { id: 'mat', label: t('held_to_mat'), n: counts.mat, color: KIND_COLOR.mat },
    { id: 'ki', label: t('knocked_in'), n: counts.ki, color: KIND_COLOR.ki },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }} className="fade-up">
      <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('explorer_intro')}</div>

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
        <button className="btn btn--ghost" style={{ marginLeft: 'auto', padding: '6px 12px' }} onClick={() => setSeedKey((k) => k + 1)}>
          <Icon name="refresh" size={14} /> {t('explorer_resample')}
        </button>
      </div>

      <Panel pad={14} right={`${t('explorer_showing')} ${shown.toLocaleString()} ${t('explorer_of')} ${data.n_total.toLocaleString()} ${t('explorer_sampled')}`}>
        <div style={{ height: 440 }}><Figure fig={fig} /></div>
      </Panel>
    </div>
  )
}
