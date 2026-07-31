import { useI18n } from '../i18n/I18nProvider'
import { participationRedemption } from '../lib/participation'
import { pct, pctSigned } from '../lib/format'
import type { NoteTerms, SimSummary } from '../api/types'

/* Cliquet participation, explained as a SERIES of graphs — one mini payoff curve
   per reset period. Each period is an independent participation bet on that
   period's basket move (strike resets to par, capped by the per-period cap); the
   locked-in P&Ls sum into the final redemption. Each mini marks that period's
   average simulated basket move (a dot on the curve) and its inter-quartile band,
   so you can see where the period typically lands and what it locks in. */

const MINI_W = 200, MINI_H = 150
const X0 = 30, X1 = 188, Y0 = 12, Y1 = 116

function Mini({ terms, k, moveMean, incMean, p25, p75 }: {
  terms: NoteTerms; k: number; moveMean: number; incMean: number; p25: number; p75: number
}) {
  const { t } = useI18n()
  // Per-period effective terms: reset strike = par, cap = per-period cap.
  const eff: NoteTerms = { ...terms, participation_periodic: false, participation_strike: 1,
                           upside_cap: terms.period_cap ?? null }
  const xMin = 0.6, xMax = 1.4
  const N = 60
  const xs: number[] = []
  for (let i = 0; i <= N; i++) xs.push(xMin + (i / N) * (xMax - xMin))
  const rs = xs.map((b) => participationRedemption(b, eff))
  const yLo = Math.min(0.8, Math.floor(Math.min(...rs) * 10) / 10)
  const yHi = Math.max(1.2, Math.ceil(Math.max(...rs) * 10) / 10)

  const mapX = (b: number) => X0 + ((b - xMin) / (xMax - xMin)) * (X1 - X0)
  const mapY = (r: number) => Y1 - ((r - yLo) / (yHi - yLo)) * (Y1 - Y0)
  const clampX = (b: number) => Math.min(xMax, Math.max(xMin, b))

  const curve = xs.map((b, i) => `${mapX(b).toFixed(1)},${mapY(rs[i]).toFixed(1)}`).join(' ')
  const meanB = clampX(1 + moveMean)
  const meanR = participationRedemption(meanB, eff)
  const bandLo = clampX(1 + p25), bandHi = clampX(1 + p75)

  return (
    <div className="card" style={{ padding: '10px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 2 }}>
        <span style={{ fontSize: 12, fontWeight: 600 }}>{t('cliquet_period', { k })}</span>
        <span className="mono" style={{ fontSize: 11, color: incMean >= 0 ? 'var(--green)' : 'var(--red)' }}>{pctSigned(incMean, 2)}</span>
      </div>
      <svg viewBox={`0 0 ${MINI_W} ${MINI_H}`} width="100%" style={{ display: 'block', fontFamily: 'var(--font-sans)' }}>
        {/* IQR move band */}
        <rect x={mapX(bandLo)} y={Y0} width={Math.max(1, mapX(bandHi) - mapX(bandLo))} height={Y1 - Y0}
              fill="var(--accent)" opacity={0.07} />
        {/* par gridlines */}
        <line x1={X0} y1={mapY(1)} x2={X1} y2={mapY(1)} stroke="var(--border-strong)" strokeWidth={0.5} />
        <line x1={mapX(1)} y1={Y0} x2={mapX(1)} y2={Y1} stroke="var(--border)" strokeWidth={0.5} strokeDasharray="2 2" />
        {/* y ticks (par + extremes) */}
        {[yLo, 1, yHi].map((r) => (
          <text key={r} x={X0 - 3} y={mapY(r) + 3} fontSize={8} fill="var(--text-muted)" textAnchor="end">{pct(r, 0)}</text>
        ))}
        {[xMin, 1, xMax].map((b) => (
          <text key={b} x={mapX(b)} y={Y1 + 11} fontSize={8} fill="var(--text-muted)" textAnchor="middle">{pct(b, 0)}</text>
        ))}
        {/* payoff curve */}
        <polyline points={curve} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" />
        {/* expected move marker */}
        <line x1={mapX(meanB)} y1={Y0} x2={mapX(meanB)} y2={Y1} stroke="var(--text)" strokeWidth={0.5} opacity={0.35} />
        <circle cx={mapX(meanB)} cy={mapY(meanR)} r={3} fill="var(--accent)" stroke="#fff" strokeWidth={1} />
        {/* axis labels */}
        <text x={(X0 + X1) / 2} y={MINI_H - 1} fontSize={8.5} fill="var(--text-faint)" textAnchor="middle">{t('cliquet_move_axis')}</text>
      </svg>
      <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textAlign: 'center', marginTop: 2 }}>
        {t('cliquet_mini_caption', { move: pctSigned(moveMean, 1) })}
      </div>
    </div>
  )
}

export default function CliquetProfiles({ terms, summary }: { terms: NoteTerms; summary: SimSummary }) {
  const { t } = useI18n()
  const moves = summary.period_move_mean
  const incs = summary.period_income_mean
  const p25 = summary.period_move_p25
  const p75 = summary.period_move_p75
  if (!moves || !incs) return null
  const n = moves.length
  // The per-period arrays are aligned to the PRICED WINDOW, so on a held note the
  // first mini is term-sheet period `period_offset + 1`, not 1. Labelling them
  // 1..n renumbered the remaining resets from scratch — the same offset contract
  // MCTables, HeroMetrics and PathInspector already follow.
  const off = summary.period_offset ?? 0

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 600,
                       color: 'var(--accent-text)', background: 'var(--accent-weak)', border: '1px solid var(--accent)',
                       borderRadius: 999, padding: '3px 12px', letterSpacing: '0.02em' }}>
          ↻ {t('grp_cliquet')} · {t('part_reset')}: {t(`freq_${terms.payment_freq}`)}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
        {Array.from({ length: n }, (_, k) => (
          <Mini key={k} terms={terms} k={k + 1 + off} moveMean={moves[k]} incMean={incs[k]}
                p25={p25?.[k] ?? moves[k]} p75={p75?.[k] ?? moves[k]} />
        ))}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 8, textAlign: 'center', lineHeight: 1.5 }}>
        {t('cliquet_caption')}
      </div>
    </div>
  )
}
