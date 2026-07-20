import { useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { participationRedemption } from '../lib/participation'
import { pct } from '../lib/format'
import type { NoteTerms, SimSummary } from '../api/types'

/* Payoff-profile diagram for a Participation Note: redemption (y) versus the final
   basket level (x). The curve is sampled from the same redemption formula the engine
   prices (lib/participation), so picture == payoff.

   With a run's `summary`, it overlays what the SIMULATION actually did: a density
   strip of the final-basket distribution along the x-axis (where outcomes land vs
   the kinks), a breakeven marker, and the expected redemption + p5–p95 band. Hover
   the plot to read (basket level → redemption). Without a summary it's curve-only —
   the setup structure diagram. */
const VIEW_W = 760, VIEW_H = 250
const X0 = 88, X1 = 620, Y_TOP = 26, Y_BOT = 188

export default function ParticipationProfile({ terms, summary }: { terms: NoteTerms; summary?: SimSummary }) {
  const { t } = useI18n()
  const [hoverB, setHoverB] = useState<number | null>(null)

  // In periodic (cliquet) mode the profile is ONE period's payoff — the same chosen
  // downside × upside profile, but off a reset strike (par) with the per-period cap.
  const periodic = terms.participation_periodic ?? false
  const eff: NoteTerms = periodic
    ? { ...terms, participation_strike: 1, upside_cap: terms.period_cap ?? null }
    : terms
  const pd = eff.participation_downside ?? 'full'
  const strike = eff.participation_strike ?? 1
  const prot = eff.protection_level ?? 1
  const cap = eff.upside_cap != null ? 1 + eff.upside_cap : Infinity

  // The distribution overlay only makes sense for a single-maturity note (cliquet's
  // x-axis is a per-period move, not the sampled final basket).
  const dist = !periodic ? summary?.final_basket_sample : undefined
  const be = !periodic ? summary?.breakeven_level ?? null : null
  const eR = !periodic ? summary?.expected_redemption ?? null : null
  const p5 = !periodic ? summary?.p5_redemption ?? null : null
  const p95 = !periodic ? summary?.p95_redemption ?? null : null

  // x-domain: 40%..180%, stretched to include a shark-fin knock-out if higher.
  // `zoom` (>1) widens the visible basket range around par so the user can zoom
  // out to see redemption at more extreme final levels (the deep-loss floor, an
  // uncapped upside, a far knock-out).
  const [zoom, setZoom] = useState(1)
  const baseMin = 0.4
  const baseMax = Math.max(1.8, (eff.knockout_level ?? 0) + 0.2)
  const xMin = Math.max(0, 1 - (1 - baseMin) * zoom)
  const xMax = 1 + (baseMax - 1) * zoom
  const N = 120
  const EPS = 1e-3
  const breaks = [strike, eff.knockout_level ?? NaN].flatMap((b) => [b - EPS, b])
  const xset = new Set<number>()
  for (let i = 0; i <= N; i++) xset.add(xMin + (i / N) * (xMax - xMin))
  for (const b of breaks) if (Number.isFinite(b) && b > xMin && b < xMax) xset.add(b)
  const xs = [...xset].sort((a, b) => a - b)
  const rs = xs.map((b) => participationRedemption(b, eff))
  const yLo = Math.min(0.6, Math.floor(Math.min(...rs) * 10) / 10)
  const yHi = Math.max(1.4, Math.ceil(Math.max(...rs) * 10) / 10)

  const mapX = (b: number) => X0 + ((b - xMin) / (xMax - xMin)) * (X1 - X0)
  const mapY = (r: number) => Y_BOT - ((r - yLo) / (yHi - yLo)) * (Y_BOT - Y_TOP)
  const invX = (px: number) => xMin + ((px - X0) / (X1 - X0)) * (xMax - xMin)
  const inY = (r: number) => r >= yLo && r <= yHi
  const clampB = (b: number) => Math.min(xMax, Math.max(xMin, b))

  const curve = xs.map((b, i) => `${mapX(b).toFixed(1)},${mapY(rs[i]).toFixed(1)}`)
  const path = curve.join(' ')

  // Filled zones under the curve: profit (above par) green, loss (below par) red.
  // Build by clipping the curve+par-line into an area polygon per sign region.
  const parY = mapY(1)
  const areaAbove = `${mapX(xs[0]).toFixed(1)},${parY.toFixed(1)} ${path} ${mapX(xs[xs.length - 1]).toFixed(1)},${parY.toFixed(1)}`

  // Density strip of the final-basket distribution along the bottom of the plot.
  const STRIP_H = 34
  let densityPath = ''
  if (dist && dist.length) {
    const BINS = 48
    const counts = new Array(BINS).fill(0)
    for (const b of dist) {
      const bb = clampB(b)
      const k = Math.min(BINS - 1, Math.floor(((bb - xMin) / (xMax - xMin)) * BINS))
      counts[k]++
    }
    const mx = Math.max(...counts, 1)
    const base = Y_BOT
    const pts = counts.map((c, k) => {
      const x = mapX(xMin + ((k + 0.5) / BINS) * (xMax - xMin))
      const y = base - (c / mx) * STRIP_H
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    densityPath = `${mapX(xMin).toFixed(1)},${base} ${pts.join(' ')} ${mapX(xMax).toFixed(1)},${base}`
  }

  const yTicks: number[] = []
  for (let r = Math.ceil(yLo * 5) / 5; r <= yHi + 1e-9; r += 0.2) yTicks.push(+r.toFixed(2))
  const xTicks = [0.5, 1.0, 1.5, 2.0].filter((b) => b >= xMin && b <= xMax)
  const gridcol = 'var(--border)'
  const hoverR = hoverB != null ? participationRedemption(hoverB, eff) : null

  const zoomBtn: React.CSSProperties = {
    width: 24, height: 24, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    padding: 0, fontSize: 15, lineHeight: 1, borderRadius: 6,
  }
  return (
    <div style={{ width: '100%' }}>
      {/* Zoom the visible basket-level range: − widens (zoom out), + narrows back. */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 4, marginBottom: 2 }}>
        <button className="btn btn--ghost" style={zoomBtn} aria-label={t('pp_zoom_out')} title={t('pp_zoom_out')}
                disabled={zoom >= 4} onClick={() => setZoom((z) => Math.min(4, +(z * 1.4).toFixed(3)))}>−</button>
        <button className="btn btn--ghost" style={zoomBtn} aria-label={t('pp_zoom_in')} title={t('pp_zoom_in')}
                disabled={zoom <= 1} onClick={() => setZoom((z) => Math.max(1, +(z / 1.4).toFixed(3)))}>+</button>
      </div>
      {periodic && (
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 6 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 600,
                         color: 'var(--accent-text)', background: 'var(--accent-weak)', border: '1px solid var(--accent)',
                         borderRadius: 999, padding: '3px 12px', letterSpacing: '0.02em' }}>
            ↻ {t('grp_cliquet')} · {t('part_reset')}: {t(`freq_${terms.payment_freq}`)}
          </span>
        </div>
      )}
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} width="100%" role="img"
           style={{ display: 'block', fontFamily: 'var(--font-sans)' }}
           onMouseLeave={() => setHoverB(null)}
           onMouseMove={(e) => {
             const r = e.currentTarget.getBoundingClientRect()
             const vx = ((e.clientX - r.left) / r.width) * VIEW_W   // px → viewBox x
             if (vx >= X0 && vx <= X1) setHoverB(clampB(invX(vx)))
             else setHoverB(null)
           }}>
        <title>{t('sec_participation')}</title>
        {/* zone shading (only with a run, so the setup diagram stays clean) */}
        {dist && (<>
          <polygon points={areaAbove} fill="var(--accent)" opacity={0.06} />
        </>)}
        {/* y grid + ticks */}
        {yTicks.map((r) => (
          <g key={`y${r}`}>
            <line x1={X0} y1={mapY(r)} x2={X1} y2={mapY(r)}
                  stroke={r === 1 ? 'var(--border-strong)' : gridcol} strokeWidth={r === 1 ? 1 : 0.5} />
            <text x={X0 - 8} y={mapY(r) + 3.5} fontSize={11} fill="var(--text-muted)" textAnchor="end">{pct(r, 0)}</text>
          </g>
        ))}
        {xTicks.map((b) => (
          <text key={`x${b}`} x={mapX(b)} y={Y_BOT + 16} fontSize={11} fill="var(--text-muted)" textAnchor="middle">{pct(b, 0)}</text>
        ))}
        {/* final-basket density strip */}
        {densityPath && <polygon points={densityPath} fill="var(--text-muted)" opacity={0.16} />}
        {/* p5–p95 redemption band on the y-axis */}
        {p5 != null && p95 != null && inY(p5) && inY(p95) && (
          <rect x={X0} y={mapY(p95)} width={X1 - X0} height={Math.max(1, mapY(p5) - mapY(p95))}
                fill="var(--accent)" opacity={0.05} />
        )}
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
        {/* expected redemption (from the run) */}
        {eR != null && inY(eR) && (
          <g>
            <line x1={X0} y1={mapY(eR)} x2={X1} y2={mapY(eR)} stroke="var(--accent)" strokeWidth={1.25} strokeDasharray="1 3" opacity={0.9} />
            <text x={X1 - 2} y={mapY(eR) - 4} fontSize={10} fill="var(--accent-text)" textAnchor="end">E[R] {pct(eR, 1)}</text>
          </g>
        )}
        {/* breakeven (loss below this basket level) */}
        {be != null && be > xMin && be < xMax && (
          <g>
            <line x1={mapX(be)} y1={Y_TOP} x2={mapX(be)} y2={Y_BOT} stroke="var(--red)" strokeWidth={1} strokeDasharray="2 2" opacity={0.7} />
            <text x={mapX(be)} y={Y_TOP - 4} fontSize={10} fill="var(--red)" textAnchor="middle">{t('pp_breakeven')} {pct(be, 0)}</text>
          </g>
        )}
        {/* direct-underlying 1:1 reference */}
        {(() => { const dLo = Math.max(xMin, yLo), dHi = Math.min(xMax, yHi)
          return <line x1={mapX(dLo)} y1={mapY(dLo)} x2={mapX(dHi)} y2={mapY(dHi)} stroke="var(--text-muted)" strokeWidth={1} strokeDasharray="2 4" opacity={0.6} /> })()}
        {/* payoff curve */}
        <polyline points={path} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" />
        {/* hover readout */}
        {hoverB != null && hoverR != null && inY(hoverR) && (
          <g>
            <line x1={mapX(hoverB)} y1={Y_TOP} x2={mapX(hoverB)} y2={Y_BOT} stroke="var(--text)" strokeWidth={0.5} opacity={0.4} />
            <circle cx={mapX(hoverB)} cy={mapY(hoverR)} r={3.5} fill="var(--accent)" stroke="#fff" strokeWidth={1} />
            <g transform={`translate(${Math.min(mapX(hoverB) + 8, X1 - 96)}, ${Math.max(mapY(hoverR) - 26, Y_TOP + 2)})`}>
              <rect width={94} height={22} rx={4} fill="var(--surface-2)" stroke="var(--border)" />
              <text x={7} y={14} fontSize={10.5} fill="var(--text)">{pct(hoverB, 0)} → {pct(hoverR, 1)}</text>
            </g>
          </g>
        )}
        {/* axes */}
        <line x1={X0} y1={Y_TOP} x2={X0} y2={Y_BOT} stroke="var(--border-strong)" strokeWidth={1} />
        <line x1={X0} y1={Y_BOT} x2={X1} y2={Y_BOT} stroke="var(--border-strong)" strokeWidth={1} />
        <text x={(X0 + X1) / 2} y={VIEW_H - 4} fontSize={11.5} fill="var(--text)" textAnchor="middle">{periodic ? t('pp_x_axis_period') : t('pp_x_axis')}</text>
        <text x={16} y={(Y_TOP + Y_BOT) / 2} fontSize={11.5} fill="var(--text)" textAnchor="middle"
              transform={`rotate(-90 16 ${(Y_TOP + Y_BOT) / 2})`}>{t('pp_y_axis')}</text>
      </svg>
      {periodic
        ? <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, textAlign: 'center', lineHeight: 1.5 }}>{t('pp_periodic_caption')}</div>
        : dist && <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 4, textAlign: 'center', lineHeight: 1.5 }}>{t('pp_dist_caption')}</div>}
    </div>
  )
}
