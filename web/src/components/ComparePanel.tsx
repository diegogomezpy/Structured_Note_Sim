import { useMemo, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import type { BacktestResult, CompareResult, ConfigMeta, LiveResult, NoteTerms } from '../api/types'
import type { RunOpts } from './SetupRail'
import Panel from './Panel'
import Figure from './Figure'
import Icon from './Icon'
import NoteTimeline from './NoteTimeline'
import SettingsOverlay from './SettingsOverlay'
import ErrorState from './ErrorState'
import { Select } from './fields'
import { pct, pctSigned, num } from '../lib/format'
import { noteSummary } from '../lib/terms'

/* A/B comparison: price the current note (A) against a variant (B) and show the
   differences across Monte Carlo, historical backtest and current performance. B
   is seeded by duplicating A or loading a saved note, then edited through the same
   SettingsOverlay. The backend prices Monte Carlo on ONE shared simulation when A
   and B share underlyings + maturity, so those differences are pure term effects. */

type Dir = 'up' | 'down' | 'neutral'
type Kind = 'pct' | 'years'
interface Row { label: string; a: number | null; b: number | null; delta: number | null; dir: Dir; kind: Kind }

// Monte Carlo diff keys → label/direction/format (server returns the A/B/Δ values).
const MC_METRICS: Record<string, { labelKey: string; dir: Dir; kind: Kind }> = {
  expected_irr:            { labelKey: 'expected_irr',          dir: 'up',      kind: 'pct' },
  expected_total_return:   { labelKey: 'expected_total_return', dir: 'up',      kind: 'pct' },
  expected_coupon:         { labelKey: 'expected_coupon',       dir: 'up',      kind: 'pct' },
  expected_nominal_payout: { labelKey: 'expected_redemption',   dir: 'up',      kind: 'pct' },
  prob_autocall:           { labelKey: 'p_autocall',            dir: 'neutral', kind: 'pct' },
  prob_knock_in_total:     { labelKey: 'p_knock_in',            dir: 'down',    kind: 'pct' },
  avg_time_to_autocall:    { labelKey: 'avg_time_autocall',     dir: 'neutral', kind: 'years' },
  expected_gain:           { labelKey: 'expected_gain',         dir: 'up',      kind: 'pct' },
  prob_above_par:          { labelKey: 'p_above_par',           dir: 'up',      kind: 'pct' },
  prob_at_cap:             { labelKey: 'p_at_cap',              dir: 'neutral', kind: 'pct' },
  prob_knocked_out:        { labelKey: 'p_knocked_out',         dir: 'down',    kind: 'pct' },
  p5_redemption:           { labelKey: 'p5_redemption',         dir: 'up',      kind: 'pct' },
}
// Backtest summary keys → label/direction/format (diff computed client-side).
const BT_METRICS: [string, string, Dir, Kind][] = [
  ['mean_irr',             'bt_mean_irr',      'up',      'pct'],
  ['median_irr',           'bt_median_irr',    'up',      'pct'],
  ['prob_called',          'bt_called_rate',   'neutral', 'pct'],
  ['prob_knock_in',        'bt_ki_rate',       'down',    'pct'],
  ['loss_given_knock_in',  'loss_given_ki',    'down',    'pct'],
  ['avg_time_to_autocall', 'avg_time_autocall','neutral', 'years'],
]

const fmtVal = (v: number | null | undefined, kind: Kind) =>
  v == null ? '—' : kind === 'years' ? `${num(v, 2)} y` : pct(v, 1)
const fmtDelta = (d: number | null, kind: Kind) =>
  d == null ? '—' : kind === 'years' ? `${d >= 0 ? '+' : ''}${num(d, 2)} y` : pctSigned(d, 1)
const deltaTone = (dir: Dir, d: number | null) => {
  if (d == null || dir === 'neutral' || Math.abs(d) < 1e-9) return 'var(--text-muted)'
  return (dir === 'up' ? d > 0 : d < 0) ? 'var(--accent-text)' : 'var(--red)'
}

export default function ComparePanel({ terms, opts, cppAvailable, configs, variantB, onVariantBChange }: {
  terms: NoteTerms
  opts: RunOpts
  cppAvailable: boolean
  configs: ConfigMeta[]
  variantB: NoteTerms | null
  onVariantBChange: (t: NoteTerms | null) => void
}) {
  const { t, lang } = useI18n()
  const setVariantB = onVariantBChange
  const [bOpts, setBOpts] = useState<RunOpts>(opts)
  const [result, setResult] = useState<CompareResult | null>(null)
  const [status, setStatus] = useState<'idle' | 'running' | 'error'>('idle')
  const [error, setError] = useState('')
  const [editingB, setEditingB] = useState(false)
  const [ranSig, setRanSig] = useState('')

  // Backtest + live are compared on demand (each is its own fetch per note).
  const [bt, setBt] = useState<{ a: BacktestResult; b: BacktestResult } | null>(null)
  const [btStatus, setBtStatus] = useState<'idle' | 'running' | 'error'>('idle')
  const [btError, setBtError] = useState('')
  const [live, setLive] = useState<{ a: LiveResult; b: LiveResult } | null>(null)
  const [liveStatus, setLiveStatus] = useState<'idle' | 'running' | 'error'>('idle')
  const [liveError, setLiveError] = useState('')

  const sig = useMemo(() => JSON.stringify({ a: terms, b: variantB, o: opts }), [terms, variantB, opts])
  const stale = !!result && ranSig !== '' && ranSig !== sig

  const dupA = () => {
    setVariantB({ ...structuredClone(terms), name: `${terms.name || t('cmp_note_b')} (B)` })
    setResult(null); setBt(null); setLive(null)
  }
  const loadB = async (file: string) => {
    if (!file) return
    setError('')
    try { setVariantB(await api.config(file)); setResult(null); setBt(null); setLive(null) }
    catch (e) { setError(String(e instanceof Error ? e.message : e)) }
  }

  const runCompare = async () => {
    if (!variantB) return
    setStatus('running'); setError('')
    try {
      const r = await api.compare(terms, variantB, {
        n_paths: opts.n_paths, seed: opts.seed, calib_years: opts.calib_years, engine: opts.engine, lang,
      })
      setResult(r); setRanSig(sig); setStatus('idle')
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e)); setStatus('error')
    }
  }

  const runBacktest = async () => {
    if (!variantB) return
    setBtStatus('running'); setBtError('')
    try {
      const [a, b] = await Promise.all([api.backtest(terms, lang), api.backtest(variantB, lang)])
      setBt({ a, b }); setBtStatus('idle')
    } catch (e) {
      setBtError(String(e instanceof Error ? e.message : e)); setBtStatus('error')
    }
  }

  const runLive = async () => {
    if (!variantB) return
    setLiveStatus('running'); setLiveError('')
    try {
      const [a, b] = await Promise.all([api.live(terms, lang), api.live(variantB, lang)])
      setLive({ a, b }); setLiveStatus('idle')
    } catch (e) {
      setLiveError(String(e instanceof Error ? e.message : e)); setLiveStatus('error')
    }
  }

  const NoteChip = ({ label, name, color }: { label: string; name: string; color: string }) => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
      <span style={{ width: 10, height: 10, borderRadius: 3, background: color, flex: '0 0 auto' }} />
      <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', color: 'var(--text-faint)' }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
    </span>
  )

  const MetricTable = ({ rows }: { rows: Row[] }) => (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: 'right', color: 'var(--text-muted)', fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            <th style={{ textAlign: 'left', padding: '6px 10px' }}>{t('cmp_metric')}</th>
            <th style={{ padding: '6px 10px' }}>{t('cmp_note_a')}</th>
            <th style={{ padding: '6px 10px' }}>{t('cmp_note_b')}</th>
            <th style={{ padding: '6px 10px' }}>{t('cmp_delta')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ textAlign: 'left', padding: '8px 10px' }}>{r.label}</td>
              <td style={{ textAlign: 'right', padding: '8px 10px', fontVariantNumeric: 'tabular-nums' }}>{fmtVal(r.a, r.kind)}</td>
              <td style={{ textAlign: 'right', padding: '8px 10px', fontVariantNumeric: 'tabular-nums' }}>{fmtVal(r.b, r.kind)}</td>
              <td style={{ textAlign: 'right', padding: '8px 10px', fontVariantNumeric: 'tabular-nums', color: deltaTone(r.dir, r.delta), fontWeight: 600 }}>{fmtDelta(r.delta, r.kind)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  const mcRows: Row[] = result
    ? result.compare.diff.rows.flatMap((row) => {
        const def = MC_METRICS[row.key]
        return def ? [{ label: t(def.labelKey), a: row.a, b: row.b, delta: row.delta, dir: def.dir, kind: def.kind }] : []
      })
    : []

  const btRows: Row[] = bt
    ? BT_METRICS.map(([key, labelKey, dir, kind]) => {
        const a = (bt.a.summary as unknown as Record<string, number | null>)[key] ?? null
        const b = (bt.b.summary as unknown as Record<string, number | null>)[key] ?? null
        const delta = typeof a === 'number' && typeof b === 'number' ? b - a : null
        return { label: t(labelKey), a, b, delta, dir, kind }
      })
    : []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      {/* ── Variant B setup ─────────────────────────────────────────────── */}
      <Panel title={t('cmp_setup_title')}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
            <NoteChip label={t('cmp_note_a')} name={terms.name || '—'} color="var(--cmp-a, #15694e)" />
            <Icon name="chart" size={14} />
            {variantB
              ? <NoteChip label={t('cmp_note_b')} name={variantB.name || '—'} color="var(--cmp-b, #9a6b1a)" />
              : <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{t('cmp_no_b')}</span>}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn" onClick={dupA}><Icon name="upload" size={13} /> {t('cmp_duplicate_a')}</button>
            <div style={{ minWidth: 220 }}>
              <Select value={''} ariaLabel={t('cmp_load_b')} placeholder={t('cmp_load_b')}
                      options={[{ value: '', label: t('cmp_load_b') }, ...configs.map((c) => ({ value: c.file, label: c.name }))]}
                      onChange={loadB} />
            </div>
            {variantB && (
              <button className="btn" onClick={() => setEditingB(true)}><Icon name="chart" size={13} /> {t('cmp_edit_b')}</button>
            )}
            <div style={{ flex: 1 }} />
            <button className="btn btn--primary" disabled={!variantB || status === 'running'} onClick={runCompare}>
              <Icon name={status === 'running' ? 'spinner' : 'play'} size={14} />
              {result ? t('cmp_rerun') : t('cmp_run')}
            </button>
          </div>
          {variantB && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>{noteSummary(variantB, t)}</div>
          )}
        </div>
      </Panel>

      {stale && result && status !== 'running' && (
        <div role="status" style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '11px 16px',
          background: 'var(--amber-weak)', border: '1px solid var(--amber)',
          borderRadius: 11, fontSize: 13, color: 'var(--text)',
        }}>
          <Icon name="refresh" size={16} />
          <span style={{ flex: 1 }}>{t('cmp_stale')}</span>
          <button className="btn" onClick={runCompare} style={{ padding: '6px 12px' }}>{t('cmp_rerun')}</button>
        </div>
      )}

      {status === 'error' && <ErrorState message={error} onRetry={runCompare} />}

      {status === 'running' && (
        <Panel pad={40}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 14 }}>
            <Icon name="spinner" size={18} /> {t('loading')}
          </div>
        </Panel>
      )}

      {result && status !== 'running' && (
        <>
          {/* provenance of the comparison basis */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 9, padding: '9px 14px', fontSize: 12.5,
            borderRadius: 10, color: 'var(--text-muted)',
            background: result.compare.shared_paths ? 'var(--accent-weak)' : 'var(--surface)',
            border: `1px solid ${result.compare.shared_paths ? 'var(--accent)' : 'var(--border)'}`,
          }}>
            <Icon name={result.compare.shared_paths ? 'check' : 'info'} size={15} />
            {result.compare.shared_paths ? t('cmp_shared_paths') : t('cmp_indep_paths')}
          </div>

          <Panel title={t('cmp_diff_title')}><MetricTable rows={mcRows} /></Panel>

          <Panel title={t('cmp_charts_title')}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
              <div style={{ height: 300 }}><Figure fig={result.compare.figures.irr} name="compare_irr" /></div>
              <div style={{ height: 300 }}><Figure fig={result.compare.figures.outcome} name="compare_outcome" /></div>
            </div>
          </Panel>

          {variantB && (
            <Panel title={t('cmp_structures_title')}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 18 }}>
                <div>
                  <div style={{ marginBottom: 8 }}><NoteChip label={t('cmp_note_a')} name={terms.name || '—'} color="var(--cmp-a, #15694e)" /></div>
                  <NoteTimeline terms={terms} />
                </div>
                <div>
                  <div style={{ marginBottom: 8 }}><NoteChip label={t('cmp_note_b')} name={variantB.name || '—'} color="var(--cmp-b, #9a6b1a)" /></div>
                  <NoteTimeline terms={variantB} />
                </div>
              </div>
            </Panel>
          )}

          {/* ── Historical backtest — A vs B ─────────────────────────────── */}
          <Panel title={t('cmp_bt_title')} right={
            <button className="btn btn--ghost" style={{ padding: '4px 10px', fontSize: 12 }}
                    disabled={btStatus === 'running'} onClick={runBacktest}>
              <Icon name={btStatus === 'running' ? 'spinner' : 'refresh'} size={13} /> {bt ? t('cmp_rerun') : t('cmp_run_bt')}
            </button>
          }>
            {btStatus === 'error' && <div style={{ fontSize: 12.5, color: 'var(--red)' }}>{btError}</div>}
            {!bt && btStatus !== 'running' && <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('cmp_bt_hint')}</div>}
            {btStatus === 'running' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 13 }}>
                <Icon name="spinner" size={16} /> {t('loading')}
              </div>
            )}
            {bt && btStatus !== 'running' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <MetricTable rows={btRows} />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
                  <div>
                    <div style={{ marginBottom: 6 }}><NoteChip label={t('cmp_note_a')} name={terms.name || '—'} color="var(--cmp-a, #15694e)" /></div>
                    <div style={{ height: 280 }}><Figure fig={bt.a.figures?.irr_scatter} name="compare_bt_a" /></div>
                  </div>
                  <div>
                    <div style={{ marginBottom: 6 }}><NoteChip label={t('cmp_note_b')} name={variantB?.name || '—'} color="var(--cmp-b, #9a6b1a)" /></div>
                    <div style={{ height: 280 }}><Figure fig={bt.b.figures?.irr_scatter} name="compare_bt_b" /></div>
                  </div>
                </div>
              </div>
            )}
          </Panel>

          {/* ── Current performance — A vs B ─────────────────────────────── */}
          <Panel title={t('cmp_live_title')} right={
            <button className="btn btn--ghost" style={{ padding: '4px 10px', fontSize: 12 }}
                    disabled={liveStatus === 'running'} onClick={runLive}>
              <Icon name={liveStatus === 'running' ? 'spinner' : 'refresh'} size={13} /> {live ? t('cmp_rerun') : t('cmp_run_live')}
            </button>
          }>
            {liveStatus === 'error' && <div style={{ fontSize: 12.5, color: 'var(--red)' }}>{liveError}</div>}
            {!live && liveStatus !== 'running' && <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('cmp_live_hint')}</div>}
            {liveStatus === 'running' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 13 }}>
                <Icon name="spinner" size={16} /> {t('loading')}
              </div>
            )}
            {live && liveStatus !== 'running' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
                {([['a', terms, 'var(--cmp-a, #15694e)'], ['b', variantB, 'var(--cmp-b, #9a6b1a)']] as const).map(([key, tm, color]) => {
                  const lr = live[key]
                  return (
                    <div key={key} style={{ border: '1px solid var(--border)', borderRadius: 12, padding: 14 }}>
                      <div style={{ marginBottom: 10 }}><NoteChip label={key === 'a' ? t('cmp_note_a') : t('cmp_note_b')} name={tm?.name || '—'} color={color} /></div>
                      {!lr.available || !lr.summary
                        ? <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('report_live_na')}</div>
                        : (
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 14px', fontSize: 13 }}>
                            <span style={{ color: 'var(--text-muted)' }}>{t('live_wof_today')}</span><span style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{fmtVal(lr.summary.wof_today, 'pct')}</span>
                            <span style={{ color: 'var(--text-muted)' }}>{t('expected_irr')}</span><span style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{fmtVal(lr.summary.irr_to_date, 'pct')}</span>
                            <span style={{ color: 'var(--text-muted)' }}>{t('live_ki_buffer')}</span><span style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{fmtVal(lr.summary.ki_buffer, 'pct')}</span>
                            <span style={{ color: 'var(--text-muted)' }}>{t('live_ac_buffer')}</span><span style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{fmtVal(lr.summary.ac_buffer, 'pct')}</span>
                          </div>
                        )}
                    </div>
                  )
                })}
              </div>
            )}
          </Panel>
        </>
      )}

      {editingB && variantB && (
        <SettingsOverlay
          terms={variantB} onChange={setVariantB}
          opts={bOpts} onOptsChange={setBOpts}
          cppAvailable={cppAvailable}
          onClose={() => setEditingB(false)}
          onRun={() => { setEditingB(false); setResult(null); setBt(null); setLive(null) }}
        />
      )}
    </div>
  )
}
