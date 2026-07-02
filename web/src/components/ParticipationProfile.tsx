import { useI18n } from '../i18n/I18nProvider'
import { participationRedemption } from '../lib/participation'
import { pct } from '../lib/format'
import type { NoteTerms } from '../api/types'

/* Payoff-profile diagram for a Participation Note: redemption (y) versus the final
   basket level (x). Pure function of the terms — the curve is sampled from the same
   redemption formula the engine prices (lib/participation), so picture == payoff. */
const VIEW_W = 760, VIEW_H = 236
const X0 = 88, X1 = 620, Y_TOP = 26, Y_BOT = 188

export default function ParticipationProfile({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  const pd = terms.participation_downside ?? 'full'
  const strike = terms.participation_strike ?? 1
  const prot = terms.protection_level ?? 1
  const cap = terms.upside_cap != null ? 1 + terms.upside_cap : Infinity

  // x-domain: 40%..180%, stretched to include a shark-fin knock-out if higher.
  const xMin = 0.4
  const xMax = Math.max(1.8, (terms.knockout_level ?? 0) + 0.2)
  const N = 120
  const xs = Array.from({ length: N + 1 }, (_, i) => xMin + (i / N) * (xMax - xMin))
  const rs = xs.map((b) => participationRedemption(b, terms))
  const yLo = Math.min(0.6, Math.floor(Math.min(...rs) * 10) / 10)
  const yHi = Math.max(1.4, Math.ceil(Math.max(...rs) * 10) / 10)

  const mapX = (b: number) => X0 + ((b - xMin) / (xMax - xMin)) * (X1 - X0)
  const mapY = (r: number) => Y_BOT - ((r - yLo) / (yHi - yLo)) * (Y_BOT - Y_TOP)
  const inY = (r: number) => r >= yLo && r <= yHi

  const path = xs.map((b, i) => `${mapX(b).toFixed(1)},${mapY(rs[i]).toFixed(1)}`).join(' ')

  // Diagonal "direct underlying" 1:1 reference, clamped to the visible box.
  const dLo = Math.max(xMin, yLo), dHi = Math.min(xMax, yHi)

  // y gridlines every 20%.
  const yTicks: number[] = []
  for (let r = Math.ceil(yLo * 5) / 5; r <= yHi + 1e-9; r += 0.2) yTicks.push(+r.toFixed(2))
  const xTicks = [0.5, 1.0, 1.5, 2.0].filter((b) => b >= xMin && b <= xMax)

  const gridcol = 'var(--border)'
  return (
    <div style={{ width: '100%' }}>
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} width="100%" role="img"
           style={{ display: 'block', fontFamily: 'var(--font-sans)' }}>
        <title>{t('sec_participation')}</title>
        {/* y grid + ticks */}
        {yTicks.map((r) => (
          <g key={`y${r}`}>
            <line x1={X0} y1={mapY(r)} x2={X1} y2={mapY(r)}
                  stroke={r === 1 ? 'var(--border-strong)' : gridcol} strokeWidth={r === 1 ? 1 : 0.5} />
            <text x={X0 - 8} y={mapY(r) + 3.5} fontSize={11} fill="var(--text-muted)" textAnchor="end">{pct(r, 0)}</text>
          </g>
        ))}
        {/* x ticks */}
        {xTicks.map((b) => (
          <text key={`x${b}`} x={mapX(b)} y={Y_BOT + 16} fontSize={11} fill="var(--text-muted)" textAnchor="middle">{pct(b, 0)}</text>
        ))}
        {/* strike marker */}
        {inY(1) && (
          <line x1={mapX(strike)} y1={Y_TOP} x2={mapX(strike)} y2={Y_BOT} stroke={gridcol} strokeWidth={0.5} strokeDasharray="3 3" />
        )}
        {/* protection floor (non-bear) */}
        {pd !== 'bear' && inY(Math.min(prot, 1)) && (
          <line x1={X0} y1={mapY(Math.min(prot, 1))} x2={X1} y2={mapY(Math.min(prot, 1))}
                stroke="var(--red)" strokeWidth={1} strokeDasharray="5 4" opacity={0.7} />
        )}
        {/* cap ceiling */}
        {Number.isFinite(cap) && inY(cap) && (
          <line x1={X0} y1={mapY(cap)} x2={X1} y2={mapY(cap)} stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="5 4" opacity={0.6} />
        )}
        {/* direct-underlying reference */}
        <line x1={mapX(dLo)} y1={mapY(dLo)} x2={mapX(dHi)} y2={mapY(dHi)}
              stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="2 4" opacity={0.6} />
        {/* payoff curve */}
        <polyline points={path} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" />
        {/* axes */}
        <line x1={X0} y1={Y_TOP} x2={X0} y2={Y_BOT} stroke="var(--border-strong)" strokeWidth={1} />
        <line x1={X0} y1={Y_BOT} x2={X1} y2={Y_BOT} stroke="var(--border-strong)" strokeWidth={1} />
        <text x={(X0 + X1) / 2} y={VIEW_H - 4} fontSize={11.5} fill="var(--text)" textAnchor="middle">{t('pp_x_axis')}</text>
        <text x={16} y={(Y_TOP + Y_BOT) / 2} fontSize={11.5} fill="var(--text)" textAnchor="middle"
              transform={`rotate(-90 16 ${(Y_TOP + Y_BOT) / 2})`}>{t('pp_y_axis')}</text>
      </svg>
    </div>
  )
}
