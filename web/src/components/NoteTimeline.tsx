import { useId } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { nObs, obsFractions, autocallSchedule, hasStepDown } from '../lib/terms'
import { pct } from '../lib/format'
import type { NoteTerms } from '../api/types'

const VIEW_W = 700
const X0 = 64          // left axis gutter
const X1 = 470         // right gutter for barrier labels
const Y_TOP = 22       // top of plot (= DOMAIN level)
const Y_BOT = 150      // 0% level
const DOMAIN = 1.25    // headroom above par

const mapY = (lvl: number) => Y_BOT - (Math.min(Math.max(lvl, 0), DOMAIN) / DOMAIN) * (Y_BOT - Y_TOP)
const mapX = (frac: number) => X0 + frac * (X1 - X0)

/** Right-gutter barrier label: a coloured line-sample + text, vertically centred
    on the barrier gridline. Kept out of the plot so long (ES) labels never clip. */
function BarrierLabel({ y, color, dash, children }: { y: number; color: string; dash?: boolean; children: React.ReactNode }) {
  return (
    <g>
      <line x1={X1 + 8} y1={y} x2={X1 + 22} y2={y} stroke={color} strokeWidth="2" strokeDasharray={dash ? '4 2' : undefined} />
      <text x={X1 + 28} y={y + 3.5} fontSize="10.5" fill="var(--text-muted)">{children}</text>
    </g>
  )
}

/** Level-ladder schematic of the note: a value axis (100 / 50 / 0), observation
    nodes sitting on the par line, and the autocall / coupon / knock-in barriers
    drawn as labelled gridlines. Pure function of the terms — no simulation. */
export default function NoteTimeline({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  const uid = useId().replace(/:/g, '')
  const n = nObs(terms)
  const fracs = obsFractions(terms)
  const start = Math.min(Math.max(terms.autocall_start_period, 1), n)

  const acLevel = terms.autocall_barrier
  const cpLevel = terms.coupon_barrier
  const kiLevel = terms.knock_in_barrier
  const parY = mapY(1.0)
  const midY = mapY(0.5)
  const cpY = mapY(cpLevel)
  const kiY = mapY(kiLevel)
  const acY = mapY(acLevel)

  const barriersEqual = Math.abs(cpLevel - kiLevel) < 1e-6
  const acAtPar = Math.abs(acLevel - 1.0) < 1e-6
  const showDotLabels = n <= 10

  // Step-down autocall: a declining stepped hurdle across the autocall window.
  const stepped = hasStepDown(terms)
  const sched = stepped ? autocallSchedule(terms) : null
  const minAc = sched ? Math.min(...sched) : acLevel
  let stepPath = ''
  if (sched) {
    stepPath = `M ${X0} ${mapY(acLevel).toFixed(1)}`
    fracs.forEach((f, i) => { stepPath += ` H ${mapX(f).toFixed(1)} V ${mapY(sched[i]).toFixed(1)}` })
  }

  // Left value-axis ticks (round references). The barriers carry their exact %
  // in the right-gutter labels, so the axis stays uncluttered.
  const axisTicks: [number, number][] = [[1.0, parY], [0.5, midY], [0.0, Y_BOT]]

  return (
    <svg viewBox={`0 0 ${VIEW_W} 178`} width="100%" style={{ display: 'block', fontFamily: 'IBM Plex Sans, sans-serif' }}
         role="img" aria-label="Note structure level ladder">
      <defs>
        <linearGradient id={`ki-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--red)" stopOpacity="0.07" />
          <stop offset="100%" stopColor="var(--red)" stopOpacity="0.015" />
        </linearGradient>
      </defs>

      {/* knock-in zone (below the KI barrier) — very light, just a hint */}
      <rect x={X0} y={kiY} width={X1 - X0} height={Y_BOT - kiY} fill={`url(#ki-${uid})`} />

      {/* value-axis gridlines + left labels */}
      {axisTicks.map(([lvl, y]) => (
        <g key={lvl}>
          <line x1={X0} y1={y} x2={X1} y2={y} stroke="var(--border)" strokeWidth="1"
                opacity={lvl === 1 ? 0.9 : 0.5} />
          <text x={X0 - 10} y={y + 3.5} fontSize="10" className="mono" fill="var(--text-faint)" textAnchor="end">
            {pct(lvl, 0)}
          </text>
        </g>
      ))}

      {/* coupon / knock-in barriers as dashed gridlines */}
      {barriersEqual ? (
        <line x1={X0} y1={cpY} x2={X1} y2={cpY} stroke="var(--accent)" strokeWidth="1.3" strokeDasharray="5 3" opacity="0.8" />
      ) : (
        <>
          <line x1={X0} y1={cpY} x2={X1} y2={cpY} stroke="var(--accent)" strokeWidth="1.3" strokeDasharray="5 3" opacity="0.8" />
          <line x1={X0} y1={kiY} x2={X1} y2={kiY} stroke="var(--red)" strokeWidth="1.3" strokeDasharray="5 3" opacity="0.8" />
        </>
      )}

      {/* autocall barrier: a level gridline (or stepped hurdle), unless it sits on par */}
      {stepPath ? (
        <path d={stepPath} fill="none" stroke="var(--accent-text)" strokeWidth="1.5" strokeDasharray="5 3" opacity="0.85" />
      ) : !acAtPar ? (
        <line x1={X0} y1={acY} x2={X1} y2={acY} stroke="var(--accent-text)" strokeWidth="1.3" strokeDasharray="5 3" opacity="0.8" />
      ) : null}

      {/* right-gutter barrier labels */}
      {stepped ? (
        <BarrierLabel y={mapY(minAc)} color="var(--accent-text)" dash>
          {t('autocall_barrier').toLowerCase()} {pct(acLevel, 0)} → {pct(minAc, 0)}
        </BarrierLabel>
      ) : acAtPar ? (
        <BarrierLabel y={parY} color="var(--accent-text)">{t('autocall_barrier').toLowerCase()} {pct(acLevel, 0)}</BarrierLabel>
      ) : (
        <BarrierLabel y={acY} color="var(--accent-text)" dash>{t('autocall_barrier').toLowerCase()} {pct(acLevel, 0)}</BarrierLabel>
      )}
      {barriersEqual ? (
        <BarrierLabel y={cpY} color="var(--accent)" dash>
          {t('coupon_barrier').toLowerCase()} · {t('knock_in_barrier').toLowerCase()} {pct(cpLevel, 0)}
        </BarrierLabel>
      ) : (
        <>
          <BarrierLabel y={cpY} color="var(--accent)" dash>{t('coupon_barrier').toLowerCase()} {pct(cpLevel, 0)}</BarrierLabel>
          <BarrierLabel y={kiY} color="var(--red)" dash>{t('knock_in_barrier').toLowerCase()} {pct(kiLevel, 0)}</BarrierLabel>
        </>
      )}

      {/* par line (where the observation nodes sit) */}
      <line x1={X0} y1={parY} x2={X1} y2={parY} stroke="var(--border-strong)" strokeWidth="1.5" />

      {/* issue node */}
      <circle cx={X0} cy={parY} r={5.5} fill="var(--surface)" stroke="var(--accent)" strokeWidth="2.5" />
      <text x={X0} y={parY - 13} fontSize="9.5" fontWeight={600} fill="var(--text-muted)" textAnchor="middle">{t('issue')}</text>

      {/* observation nodes */}
      {fracs.map((f, i) => {
        const k = i + 1
        const x = mapX(f)
        const isMat = k === n
        const isCallable = k >= start
        if (isMat) {
          return (
            <g key={k}>
              <rect x={x - 5.5} y={parY - 5.5} width={11} height={11} rx={2} transform={`rotate(45 ${x} ${parY})`}
                    fill="var(--navy)" stroke="var(--navy)" strokeWidth="1.6" />
              <text x={x} y={parY - 13} fontSize="9.5" fontWeight={600} fill="var(--text-muted)" textAnchor="middle">{t('maturity_short')}</text>
              <path d={`M ${x} ${parY + 9} l 4 7 h -8 z`} fill="var(--navy)" />
            </g>
          )
        }
        return (
          <g key={k}>
            <circle cx={x} cy={parY} r={isCallable ? 5 : 4} fill={isCallable ? 'var(--accent)' : 'var(--surface)'}
                    stroke={isCallable ? 'var(--accent)' : 'var(--border-strong)'} strokeWidth="1.8" />
            {showDotLabels && (
              <text x={x} y={parY - 12} fontSize="9" fill="var(--text-faint)" textAnchor="middle">P{k}</text>
            )}
            {/* callable marker: a small up-tick below eligible nodes */}
            {isCallable && <path d={`M ${x} ${parY + 9} l 4 7 h -8 z`} fill="var(--accent)" />}
          </g>
        )
      })}

      {/* callable caption */}
      <text x={mapX((start - 1) / n) + 4} y={parY + 30} fontSize="9.5" fill="var(--accent-text)">
        ▲ {t('autocall_window').toLowerCase()}{start > 1 ? ` · P${start}+` : ''}
      </text>

      {/* footer caption */}
      <text x={X0 - 10} y={172} fontSize="10" fill="var(--text-faint)">
        {n} × {t(`freq_${terms.payment_freq}`)} · {pct(terms.coupon_pa, 1)} {t('coupon_pa').toLowerCase()}
        {terms.memory ? ` · ${t('memory').toLowerCase()}` : ''}
      </text>
    </svg>
  )
}
