import { Fragment, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import type { BacktestResult, CompareResult, ConfigMeta, LiveResult, NoteTerms } from '../api/types'
import type { RunOpts } from './SetupRail'
import Panel from './Panel'
import Figure from './Figure'
import Icon from './Icon'
import NoteTimeline from './NoteTimeline'
import OutcomeWaterfall from './OutcomeWaterfall'
import SettingsOverlay from './SettingsOverlay'
import ErrorState from './ErrorState'
import FolderConnect from './FolderConnect'
import { Select } from './fields'
import { useLocalFolder } from '../lib/localFolder'
import { pct, pctSigned, num } from '../lib/format'
import { noteSummary, termDiffRows } from '../lib/terms'

/* A/B comparison: price the current note (A) against a variant (B) and show the
   differences across Monte Carlo, historical backtest and current performance. B
   is seeded by duplicating A or loading a saved note, then edited through the same
   SettingsOverlay. The backend prices Monte Carlo on ONE shared simulation when A
   and B share underlyings + maturity, so those differences are pure term effects. */

type Dir = 'up' | 'down' | 'neutral'
type Kind = 'pct' | 'months'
interface Row { label: string; a: number | null; b: number | null; delta: number | null; dir: Dir; kind: Kind
                se?: number | null }

// Monte Carlo diff keys → label/direction/format (server returns the A/B/Δ values).
const MC_METRICS: Record<string, { labelKey: string; dir: Dir; kind: Kind }> = {
  expected_irr:            { labelKey: 'expected_irr',          dir: 'up',      kind: 'pct' },
  expected_total_return:   { labelKey: 'expected_total_return', dir: 'up',      kind: 'pct' },
  expected_coupon:         { labelKey: 'expected_coupon',       dir: 'up',      kind: 'pct' },
  expected_nominal_payout: { labelKey: 'expected_redemption',   dir: 'up',      kind: 'pct' },
  prob_autocall:           { labelKey: 'p_autocall',            dir: 'neutral', kind: 'pct' },
  prob_knock_in_total:     { labelKey: 'p_knock_in',            dir: 'down',    kind: 'pct' },
  avg_time_to_autocall:    { labelKey: 'avg_time_autocall',     dir: 'neutral', kind: 'months' },
  expected_gain:           { labelKey: 'expected_gain',         dir: 'up',      kind: 'pct' },
  prob_above_par:          { labelKey: 'p_above_par',           dir: 'up',      kind: 'pct' },
  prob_at_cap:             { labelKey: 'p_at_cap',              dir: 'neutral', kind: 'pct' },
  prob_knocked_out:        { labelKey: 'p_knocked_out',         dir: 'down',    kind: 'pct' },
  p5_redemption:           { labelKey: 'p5_redemption',         dir: 'up',      kind: 'pct' },
}
// Backtest summary keys → label/direction/format (diff computed client-side).
// `loss_given_knock_in` is quoted as a NEGATIVE return, so a positive delta is a
// shallower loss — 'up', not 'down'. Marking it 'down' painted "B loses 2.1%
// less when it knocks in" red.
const BT_METRICS: [string, string, Dir, Kind][] = [
  ['mean_irr',             'bt_mean_irr',      'up',      'pct'],
  ['median_irr',           'bt_median_irr',    'up',      'pct'],
  ['prob_called',          'bt_called_rate',   'neutral', 'pct'],
  ['prob_knock_in',        'bt_ki_rate',       'down',    'pct'],
  ['loss_given_knock_in',  'loss_given_ki',    'up',      'pct'],
  ['avg_time_to_autocall', 'avg_time_autocall','neutral', 'months'],
]

// Durations arrive in years (the engine's unit) and are quoted in months.
const fmtVal = (v: number | null | undefined, kind: Kind) =>
  v == null ? '—' : kind === 'months' ? `${num(v * 12, 1)} mo` : pct(v, 1)
const fmtDelta = (d: number | null, kind: Kind) =>
  d == null ? '—' : kind === 'months' ? `${d >= 0 ? '+' : ''}${num(d * 12, 1)} mo` : pctSigned(d, 1)
const deltaTone = (dir: Dir, d: number | null) => {
  if (d == null || dir === 'neutral' || Math.abs(d) < 1e-9) return 'var(--text-muted)'
  return (dir === 'up' ? d > 0 : d < 0) ? 'var(--accent-text)' : 'var(--red)'
}
/** A delta inside ±2 standard errors is Monte Carlo noise, not a term effect —
    without this the table invites reading a rounding artefact as a decision. */
const isNoise = (d: number | null, se: number | null | undefined) =>
  d != null && se != null && se > 0 && Math.abs(d) < 2 * se

const CMP_A = 'var(--cmp-a, #15694e)'
const CMP_B = 'var(--cmp-b, #9a6b1a)'

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

  // The user's own folder of note configs — SAME persisted handle as the setup
  // rail (keyed 'note-configs'), so whatever they can load as A is loadable as B.
  // Without this the picker only offered the handful of examples bundled in the
  // repo, which is not where anyone's real notes live.
  const local = useLocalFolder('note-configs')
  const fileRef = useRef<HTMLInputElement>(null)

  const dupA = () => {
    setVariantB({ ...structuredClone(terms), name: `${terms.name || t('cmp_note_b')} (B)` })
    setResult(null); setBt(null); setLive(null)
  }
  /** Adopt a loaded note as B and drop any results priced against the old one. */
  const adoptB = (t: NoteTerms) => {
    setVariantB(t); setResult(null); setBt(null); setLive(null)
  }
  /** Load B from the picker. Entries are either a repo-bundled example (the file
      name) or one of the user's own folder notes (`local:<name>`), which arrives as
      raw JSON and goes through the same parse endpoint the rail uses — so a legacy
      or hand-written config is migrated by NoteTerms.from_dict, not trusted as-is. */
  const loadB = async (value: string) => {
    if (!value) return
    setError('')
    try {
      if (value.startsWith('local:')) {
        const f = local.files.find((x) => `local:${x.name}` === value)
        if (!f) return
        adoptB(await api.parseConfig(f.raw))
      } else {
        adoptB(await api.config(value))
      }
    } catch (e) { setError(String(e instanceof Error ? e.message : e)) }
  }
  /** One-off JSON upload — the fallback that works with no folder connected at
      all (and on browsers without the File System Access API). */
  const uploadB = async (file: File | undefined) => {
    if (!file) return
    setError('')
    try { adoptB(await api.parseConfig(JSON.parse(await file.text()))) }
    catch { setError(t('upload_invalid')) }
    if (fileRef.current) fileRef.current.value = ''
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
          {rows.map((r) => {
            const noise = isNoise(r.delta, r.se)
            return (
              <tr key={r.label} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ textAlign: 'left', padding: '8px 10px' }}>{r.label}</td>
                <td style={{ textAlign: 'right', padding: '8px 10px', fontVariantNumeric: 'tabular-nums' }}>{fmtVal(r.a, r.kind)}</td>
                <td style={{ textAlign: 'right', padding: '8px 10px', fontVariantNumeric: 'tabular-nums' }}>{fmtVal(r.b, r.kind)}</td>
                <td style={{ textAlign: 'right', padding: '8px 10px', fontVariantNumeric: 'tabular-nums',
                             color: noise ? 'var(--text-faint)' : deltaTone(r.dir, r.delta), fontWeight: 600 }}
                    title={r.se != null ? t('cmp_se_tip', { v: pct(r.se, 3) }) : undefined}>
                  {fmtDelta(r.delta, r.kind)}
                  {noise && <span style={{ fontWeight: 400, fontSize: 11, marginLeft: 5 }}>{t('cmp_noise')}</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )

  /** The headline a table of means can't give you: how often B actually wins,
      and whether the average edge survives its own error bar. */
  const VerdictBand = ({ p }: { p: NonNullable<CompareResult['compare']['paired']> }) => {
    const solid = !isNoise(p.mean_edge, p.se_edge)
    const bWins = p.mean_edge > 0
    const tone = !solid ? 'var(--text-muted)' : bWins ? CMP_B : CMP_A
    const Tile = ({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) => (
      <div style={{ minWidth: 140 }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>
        {/* A range reads as one figure, so step the size down rather than let it
            wrap out of line with the tiles either side. */}
        <div className="mono" style={{ fontSize: value.length > 12 ? 17 : 24, fontWeight: 600,
                                       lineHeight: 1.15, whiteSpace: 'nowrap',
                                       color: color ?? 'var(--text)' }}>{value}</div>
        {sub && <div className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 6 }}>{sub}</div>}
      </div>
    )
    return (
      <Panel title={t('cmp_verdict_title')}>
        <div style={{ fontSize: 13, marginBottom: 14, color: 'var(--text)' }}>
          {solid
            ? t(bWins ? 'cmp_verdict_b' : 'cmp_verdict_a', { w: pct(bWins ? p.win_rate : p.loss_rate, 0) })
            : t('cmp_verdict_tie')}
        </div>
        <div className="stagger" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 16 }}>
          {/* The basis is named on the tile: the Monte Carlo win rate is on
              TOTAL RETURN and the backtest's is on IRR, and a note that calls
              sooner can win one and lose the other. Two tiles both reading
              "B wins" over different quantities is a trap. */}
          <Tile label={t('cmp_win_rate_tr')} value={pct(p.win_rate, 1)} color={CMP_B}
                sub={t('cmp_win_sub', { a: pct(p.loss_rate, 1), tie: pct(p.tie_rate, 1) })} />
          <Tile label={t('cmp_mean_edge_lbl')} value={pctSigned(p.mean_edge, 2)} color={tone}
                sub={p.se_edge != null ? `± ${pct(2 * p.se_edge, 2)}` : undefined} />
          <Tile label={t('cmp_median_edge')} value={pctSigned(p.median_edge, 2)} color={tone} />
          <Tile label={t('cmp_edge_range')} value={`${pctSigned(p.edge_p5, 1)} … ${pctSigned(p.edge_p95, 1)}`}
                sub={t('cmp_edge_range_sub')} />
          {p.conditional.edge_on_a_losses != null && (
            <Tile label={t('cmp_edge_on_losses')} value={pctSigned(p.conditional.edge_on_a_losses, 1)}
                  color={p.conditional.edge_on_a_losses >= 0 ? CMP_B : CMP_A}
                  sub={t('cmp_edge_on_losses_sub', { v: pct(p.conditional.a_loss_rate, 1) })} />
          )}
        </div>
      </Panel>
    )
  }

  /** Which terms actually differ. Without it the reader has to eyeball two
      structure diagrams to work out what the metric deltas are attributable to. */
  const TermDiff = () => {
    if (!variantB) return null
    const rows = termDiffRows(terms, variantB, t)
    return (
      <Panel title={t('cmp_termdiff_title')}>
        {rows.length === 0
          ? <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('cmp_termdiff_same')}</div>
          : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: 'right', color: 'var(--text-muted)', fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    <th style={{ textAlign: 'left', padding: '6px 10px' }}>{t('cmp_term')}</th>
                    <th style={{ padding: '6px 10px' }}>{t('cmp_note_a')}</th>
                    <th style={{ padding: '6px 10px' }}>{t('cmp_note_b')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.label} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ textAlign: 'left', padding: '8px 10px' }}>{r.label}</td>
                      <td className="mono" style={{ textAlign: 'right', padding: '8px 10px', color: CMP_A }}>{r.a}</td>
                      <td className="mono" style={{ textAlign: 'right', padding: '8px 10px', color: CMP_B }}>{r.b}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Panel>
    )
  }

  const mcRows: Row[] = result
    ? result.compare.diff.rows.flatMap((row) => {
        const def = MC_METRICS[row.key]
        return def ? [{ label: t(def.labelKey), a: row.a, b: row.b, delta: row.delta,
                        dir: def.dir, kind: def.kind, se: row.se }] : []
      })
    : []

  /** Backtest issues pair by ISSUE DATE — the same historical window priced two
      ways — so the same win-rate reading the Monte Carlo gets applies here, over
      real history rather than simulated paths. Null until both sides have run. */
  const btPaired = useMemo(() => {
    if (!bt) return null
    const byDate = new Map(bt.b.issues.map((i) => [i.issue_date, i.irr]))
    const pairs = bt.a.issues.flatMap((i) => {
      const b = byDate.get(i.issue_date)
      return i.irr != null && b != null ? [{ date: i.issue_date, edge: b - i.irr }] : []
    })
    if (!pairs.length) return null
    const worst = pairs.reduce((w, p) => (p.edge < w.edge ? p : w), pairs[0])
    return {
      n: pairs.length,
      winRate: pairs.filter((p) => p.edge > 0).length / pairs.length,
      meanEdge: pairs.reduce((s, p) => s + p.edge, 0) / pairs.length,
      worstEdge: worst.edge,
      worstDate: worst.date,
    }
  }, [bt])

  /** The metric table as CSV — the numbers usually end up in a deck or a mail,
      and retyping them from the screen is how transcription errors happen. */
  const exportCsv = () => {
    const head = ['metric', terms.name || 'A', variantB?.name || 'B', 'delta', 'std_error']
    const body = [...mcRows, ...btRows].map((r) => [
      r.label, r.a ?? '', r.b ?? '', r.delta ?? '', r.se ?? '',
    ])
    const csv = [head, ...body]
      .map((row) => row.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const el = document.createElement('a')
    el.href = url
    el.download = `compare_${(terms.name || 'A').replace(/[^A-Za-z0-9_-]+/g, '_')}_vs_${(variantB?.name || 'B').replace(/[^A-Za-z0-9_-]+/g, '_')}.csv`
    document.body.appendChild(el); el.click(); el.remove(); URL.revokeObjectURL(url)
  }

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
          {/* A and B, side by side with B's one-line summary under it — the
              summary used to sit at the bottom of the card, under the folder
              controls, where it read as a caption for the wrong thing. */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
            <NoteChip label={t('cmp_note_a')} name={terms.name || '—'} color={CMP_A} />
            <span style={{ fontSize: 11.5, fontWeight: 600, letterSpacing: '0.08em',
                           textTransform: 'uppercase', color: 'var(--text-faint)', lineHeight: '20px' }}>
              {t('cmp_vs')}
            </span>
            {variantB ? (
              <div style={{ minWidth: 0 }}>
                <NoteChip label={t('cmp_note_b')} name={variantB.name || '—'} color={CMP_B} />
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5, marginTop: 4 }}>
                  {noteSummary(variantB, t)}
                </div>
              </div>
            ) : <span style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: '20px' }}>{t('cmp_no_b')}</span>}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn" onClick={dupA}><Icon name="copy" size={13} /> {t('cmp_duplicate_a')}</button>
            <div style={{ minWidth: 220 }}>
              <Select value={''} ariaLabel={t('cmp_load_b')} placeholder={t('cmp_load_b')}
                      options={[
                        { value: '', label: t('cmp_load_b') },
                        ...local.files.map((f) => ({ value: `local:${f.name}`, label: `${f.name} ${t('folder_tag')}` })),
                        ...configs.map((c) => ({ value: c.file, label: c.name })),
                      ]}
                      onChange={loadB} />
            </div>
            <button className="btn" onClick={() => fileRef.current?.click()}
                    title={t('upload_config_hint')} aria-label={t('cmp_upload_b')}>
              <Icon name="upload" size={13} /> {t('cmp_upload_b')}
            </button>
            <input ref={fileRef} type="file" accept="application/json,.json" style={{ display: 'none' }}
                   onChange={(e) => uploadB(e.target.files?.[0])} />
            {variantB && (
              <button className="btn" onClick={() => setEditingB(true)}><Icon name="pencil" size={13} /> {t('cmp_edit_b')}</button>
            )}
            <div style={{ flex: 1 }} />
            <button className="btn btn--primary" disabled={!variantB || status === 'running'} onClick={runCompare}>
              <Icon name={status === 'running' ? 'spinner' : 'play'} size={14} />
              {result ? t('cmp_rerun') : t('cmp_run')}
            </button>
          </div>
          {/* Same folder controls as the setup rail, on the same persisted handle:
              connect / reconnect / refresh. Without this a user who granted access
              from the rail could still land here with an empty picker, because each
              panel holds its own copy of the folder state. */}
          <FolderConnect fld={local} />
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
          {/* Provenance of the comparison basis. When the paths could NOT be
              shared, name the terms responsible — "noisier" is not actionable,
              "the maturities differ" is. */}
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: 9, padding: '9px 14px', fontSize: 12.5,
            borderRadius: 10, color: 'var(--text-muted)', lineHeight: 1.55,
            background: result.compare.shared_paths ? 'var(--accent-weak)' : 'var(--amber-weak)',
            border: `1px solid ${result.compare.shared_paths ? 'var(--accent)' : 'var(--amber)'}`,
          }}>
            <Icon name={result.compare.shared_paths ? 'check' : 'info'} size={15} />
            <span>
              {result.compare.shared_paths ? t('cmp_shared_paths') : t('cmp_indep_paths')}
              {!result.compare.shared_paths && (result.compare.share_blockers ?? []).length > 0 && (
                <> {t('cmp_blocked_by', {
                  v: (result.compare.share_blockers ?? []).map((k) => t(`cmp_blk_${k}`)).join(', '),
                })}</>
              )}
            </span>
          </div>

          {result.compare.paired && <VerdictBand p={result.compare.paired} />}

          <TermDiff />

          <Panel title={t('cmp_diff_title')} right={
            <button className="btn btn--ghost" style={{ padding: '4px 10px', fontSize: 12 }} onClick={exportCsv}>
              <Icon name="download" size={13} /> {t('cmp_export_csv')}
            </button>
          }>
            <MetricTable rows={mcRows} />
            <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 10, lineHeight: 1.5 }}>
              {t('cmp_noise_hint')}
            </div>
          </Panel>

          {/* Paired views — only meaningful when both notes ran the same paths. */}
          {result.compare.figures.delta && (
            <Panel title={t('cmp_paired_title')}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
                <div style={{ height: 320 }}><Figure fig={result.compare.figures.delta} name="compare_delta" /></div>
                <div style={{ height: 320 }}><Figure fig={result.compare.figures.scatter} name="compare_scatter" /></div>
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 10, lineHeight: 1.5 }}>
                {t('cmp_paired_hint')}
              </div>
            </Panel>
          )}

          {result.compare.figures.transition && (
            <Panel title={t('cmp_transition_panel')}>
              <div style={{ height: 340 }}><Figure fig={result.compare.figures.transition} name="compare_transition" /></div>
              <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 10, lineHeight: 1.5 }}>
                {t('cmp_transition_hint')}
              </div>
            </Panel>
          )}

          {/* Outcomes read as the SAME proportional bar the Monte Carlo summary
              uses — one per note, stacked. A Plotly legend of three brand-tinted
              greens was illegible; this reuses the component that already
              solved it (and the PDF keeps its own chart). */}
          <Panel title={t('outcomes')}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              {([['a', terms.name], ['b', variantB?.name]] as const).map(([k, nm]) => (
                <div key={k}>
                  <div style={{ marginBottom: 8 }}>
                    <NoteChip label={k === 'a' ? t('cmp_note_a') : t('cmp_note_b')}
                              name={nm || '—'} color={k === 'a' ? CMP_A : CMP_B} />
                  </div>
                  <OutcomeWaterfall summary={result[k].summary} />
                </div>
              ))}
            </div>
          </Panel>

          <Panel title={t('cmp_charts_title')}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ height: 340 }}><Figure fig={result.compare.figures.irr} name="compare_irr" /></div>
              {result.compare.figures.fan && (
                <div style={{ height: 320 }}><Figure fig={result.compare.figures.fan} name="compare_fan" /></div>
              )}
            </div>
          </Panel>

          {variantB && (
            // Stacked, not columns. The ladder diagram carries barrier labels at
            // a fixed type size, so halving its width made them illegible — the
            // same reason the per-asset fans went full width.
            <Panel title={t('cmp_structures_title')}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                {([[t('cmp_note_a'), terms, CMP_A], [t('cmp_note_b'), variantB, CMP_B]] as const).map(([label, tm, color]) => (
                  <div key={label}>
                    <div style={{ marginBottom: 8 }}><NoteChip label={label} name={tm.name || '—'} color={color} /></div>
                    <NoteTimeline terms={tm} />
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {/* ── Historical backtest — A vs B ─────────────────────────────── */}
          <Panel title={t('cmp_bt_title')} right={
            <button className="btn btn--ghost" style={{ padding: '4px 10px', fontSize: 12 }}
                    disabled={btStatus === 'running'} onClick={runBacktest}>
              <Icon name={btStatus === 'running' ? 'spinner' : 'refresh'} size={13} /> {bt ? t('cmp_rerun_bt') : t('cmp_run_bt')}
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
                {btPaired && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 16 }}>
                    <div>
                      <div className="eyebrow" style={{ marginBottom: 6 }}>{t('cmp_bt_win_rate_irr')}</div>
                      <div className="mono" style={{ fontSize: 22, fontWeight: 600, color: CMP_B }}>{pct(btPaired.winRate, 1)}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 5 }}>
                        {t('cmp_bt_of_issues', { n: String(btPaired.n) })}
                      </div>
                    </div>
                    <div>
                      <div className="eyebrow" style={{ marginBottom: 6 }}>{t('cmp_bt_mean_edge')}</div>
                      <div className="mono" style={{ fontSize: 22, fontWeight: 600, color: btPaired.meanEdge >= 0 ? CMP_B : CMP_A }}>
                        {pctSigned(btPaired.meanEdge, 2)}
                      </div>
                    </div>
                    <div>
                      <div className="eyebrow" style={{ marginBottom: 6 }}>{t('cmp_bt_worst_edge')}</div>
                      <div className="mono" style={{ fontSize: 22, fontWeight: 600, color: btPaired.worstEdge >= 0 ? CMP_B : CMP_A }}>
                        {pctSigned(btPaired.worstEdge, 2)}
                      </div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 5 }}>{btPaired.worstDate}</div>
                    </div>
                  </div>
                )}
                <MetricTable rows={btRows} />
                {/* Full width, stacked: the issue scatter carries a per-period
                    outcome legend, which at half width overran the plot and
                    collided with the break-even annotation. */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  {([[t('cmp_note_a'), terms.name, CMP_A, bt.a.figures?.irr_scatter, 'compare_bt_a'],
                     [t('cmp_note_b'), variantB?.name, CMP_B, bt.b.figures?.irr_scatter, 'compare_bt_b']] as const).map(
                    ([label, nm, color, fig, key]) => (
                      <div key={key}>
                        <div style={{ marginBottom: 6 }}><NoteChip label={label} name={nm || '—'} color={color} /></div>
                        <div style={{ height: 320 }}><Figure fig={fig} name={key} /></div>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </Panel>

          {/* ── Current performance — A vs B ─────────────────────────────── */}
          <Panel title={t('cmp_live_title')} right={
            <button className="btn btn--ghost" style={{ padding: '4px 10px', fontSize: 12 }}
                    disabled={liveStatus === 'running'} onClick={runLive}>
              <Icon name={liveStatus === 'running' ? 'spinner' : 'refresh'} size={13} /> {live ? t('cmp_rerun_live') : t('cmp_run_live')}
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
                {([['a', terms, CMP_A], ['b', variantB, CMP_B]] as const).map(([key, tm, color]) => {
                  const lr = live[key]
                  return (
                    <div key={key} style={{ border: '1px solid var(--border)', borderRadius: 12, padding: 14 }}>
                      <div style={{ marginBottom: 10 }}><NoteChip label={key === 'a' ? t('cmp_note_a') : t('cmp_note_b')} name={tm?.name || '—'} color={color} /></div>
                      {!lr.available || !lr.summary
                        ? <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>{t('report_live_na')}</div>
                        : (
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '8px 14px', fontSize: 13 }}>
                            {([
                              ['live_wof_today', lr.summary.wof_today],
                              ['live_coupons_paid', lr.summary.total_coupons],
                              ['live_irr_to_date', lr.summary.irr_to_date],
                              ['live_ki_buffer', lr.summary.ki_buffer],
                              ['live_ac_buffer', lr.summary.ac_buffer],
                              // Position rows appear only for a secondary purchase,
                              // where the note's own numbers aren't the holder's.
                              ...(lr.summary.secondary ? [
                                ['cost_basis', lr.summary.cost_basis],
                                ['live_income_since', lr.summary.income_since],
                                ['live_return_on_cost', lr.summary.return_on_cost],
                              ] as [string, number | null | undefined][] : []),
                            ] as [string, number | null | undefined][]).map(([k, v]) => (
                              <Fragment key={k}>
                                <span style={{ color: 'var(--text-muted)' }}>{t(k)}</span>
                                <span className="mono" style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{fmtVal(v, 'pct')}</span>
                              </Fragment>
                            ))}
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
