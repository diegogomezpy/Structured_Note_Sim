import { useId } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { nObs, obsFractions, autocallSchedule, hasStepDown } from '../lib/terms'
import { pct } from '../lib/format'
import type { NoteTerms } from '../api/types'

const X0 = 40
const X1 = 486        // leaves a right gutter for the (longer in ES) barrier labels
const VIEW_W = 700
const Y_TOP = 26
const Y_BOT = 132
const DOMAIN = 1.22   // level mapped to the top of the plot area

const mapY = (level: number) => Y_BOT - (Math.min(level, DOMAIN) / DOMAIN) * (Y_BOT - Y_TOP)
const mapX = (frac: number) => X0 + frac * (X1 - X0)

/** Right-gutter barrier label: a coloured tick + text, vertically centred on the
    barrier line. Kept out of the plot area so long (Spanish) labels never clip. */
function BarrierLabel({ y, color, children }: { y: number; color: string; children: React.ReactNode }) {
  return (
    <g>
      <rect x={X1 + 6} y={y - 5} width={10} height={10} rx={2.5} fill={color} opacity={0.9} />
      <text x={X1 + 22} y={y + 3.5} fontSize="10.5" fill="var(--text-muted)">{children}</text>
    </g>
  )
}

/** Live schematic of the note: par baseline, observation timeline, autocall
    window, and the barrier reference lines with a shaded knock-in loss zone.
    Pure function of the terms — no simulation. */
export default function NoteTimeline({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  const uid = useId().replace(/:/g, '')
  const n = nObs(terms)
  const fracs = obsFractions(terms)
  const start = Math.min(Math.max(terms.autocall_start_period, 1), n)

  const acLevel = terms.autocall_barrier
  const cpLevel = terms.coupon_barrier
  const kiLevel = terms.knock_in_barrier
  const parY = mapY(acLevel)            // baseline = the par / autocall-100% reference
  const acX = mapX((start - 1) / n)     // autocall window opens just before period `start`

  const barriersEqual = Math.abs(cpLevel - kiLevel) < 1e-6
  const showDotLabels = n <= 8

  // Step-down autocall: a declining stepped hurdle across the autocall window.
  const stepped = hasStepDown(terms)
  const sched = stepped ? autocallSchedule(terms) : null
  const minAc = sched ? Math.min(...sched) : acLevel
  let stepPath = ''
  if (sched) {
    stepPath = `M ${X0} ${mapY(acLevel).toFixed(1)}`
    fracs.forEach((f, i) => { stepPath += ` H ${mapX(f).toFixed(1)} V ${mapY(sched[i]).toFixed(1)}` })
  }

  const kiY = mapY(kiLevel)
  const cpY = mapY(cpLevel)

  return (
    <svg viewBox={`0 0 ${VIEW_W} 170`} width="100%" style={{ display: 'block', fontFamily: 'IBM Plex Sans, sans-serif' }}
         role="img" aria-label="Note structure timeline">
      <defs>
        <linearGradient id={`band-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.03" />
        </linearGradient>
        <linearGradient id={`loss-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--red)" stopOpacity="0.10" />
          <stop offset="100%" stopColor="var(--red)" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id={`axis-${uid}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--border-strong)" />
          <stop offset={`${((acX - X0) / (X1 - X0)) * 100}%`} stopColor="var(--border-strong)" />
          <stop offset={`${((acX - X0) / (X1 - X0)) * 100}%`} stopColor="var(--accent)" />
          <stop offset="100%" stopColor="var(--accent)" />
        </linearGradient>
      </defs>

      {/* framed plot area */}
      <rect x={X0 - 14} y={Y_TOP - 10} width={X1 - X0 + 30} height={Y_BOT - Y_TOP + 28} rx={12}
            fill="var(--surface-2)" opacity="0.45" stroke="var(--border)" strokeWidth="1" />

      {/* knock-in loss zone (below the KI barrier) */}
      <rect x={X0 - 8} y={kiY} width={X1 - X0 + 16} height={Y_BOT + 2 - kiY} rx={4} fill={`url(#loss-${uid})`} />

      {/* autocall window band + caption (below the axis so it never collides
          with the per-period dot labels above) */}
      <rect x={acX} y={Y_TOP - 4} width={X1 - acX} height={parY - Y_TOP + 8} rx={7} fill={`url(#band-${uid})`} />
      <line x1={acX} y1={Y_TOP - 4} x2={acX} y2={parY + 4} stroke="var(--accent)" strokeWidth="1" strokeDasharray="2 3" opacity="0.5" />
      <text x={acX + 6} y={parY + 16} fontSize="9.5" fontWeight={600} fill="var(--accent-text)" letterSpacing="0.02em">
        {t('autocall_window').toUpperCase()}
      </text>

      {/* barrier reference lines */}
      <line x1={X0} y1={cpY} x2={X1} y2={cpY} stroke="var(--accent)" strokeWidth="1.2" strokeDasharray="4 3" opacity="0.7" />
      {!barriersEqual && (
        <line x1={X0} y1={kiY} x2={X1} y2={kiY} stroke="var(--red)" strokeWidth="1.2" strokeDasharray="4 3" opacity="0.75" />
      )}

      {/* step-down autocall hurdle */}
      {stepPath && (
        <path d={stepPath} fill="none" stroke="var(--text-muted)" strokeWidth="1.4" strokeDasharray="5 3" opacity="0.85" />
      )}

      {/* right-gutter barrier labels */}
      <BarrierLabel y={parY} color="var(--accent)">
        {t('autocall_barrier').toLowerCase()} {stepped ? `${pct(acLevel, 0)} → ${pct(minAc, 0)}` : pct(acLevel, 0)}
      </BarrierLabel>
      {barriersEqual ? (
        <BarrierLabel y={cpY} color="var(--accent)">
          {t('coupon_barrier').toLowerCase()} · {t('knock_in_barrier').toLowerCase()} {pct(cpLevel, 0)}
        </BarrierLabel>
      ) : (
        <>
          <BarrierLabel y={cpY} color="var(--accent)">{t('coupon_barrier').toLowerCase()} {pct(cpLevel, 0)}</BarrierLabel>
          <BarrierLabel y={kiY} color="var(--red)">{t('knock_in_barrier').toLowerCase()} {pct(kiLevel, 0)}</BarrierLabel>
        </>
      )}

      {/* par baseline / observation axis (muted before autocall, accent within) */}
      <line x1={X0} y1={parY} x2={X1} y2={parY} stroke={`url(#axis-${uid})`} strokeWidth="2" strokeLinecap="round" />
      <text x={X0 - 18} y={parY + 3.5} fontSize="9.5" className="mono" fill="var(--text-faint)" textAnchor="end">100%</text>

      {/* issue marker */}
      <circle cx={X0} cy={parY} r={5.5} fill="var(--surface)" stroke="var(--accent)" strokeWidth="2.5" />
      <text x={X0} y={parY - 13} fontSize="9.5" fontWeight={600} fill="var(--text-muted)" textAnchor="middle">{t('issue')}</text>

      {/* observation dots */}
      {fracs.map((f, i) => {
        const k = i + 1
        const x = mapX(f)
        const isMat = k === n
        const isAutocall = k >= start
        if (isMat) {
          // maturity: a small diamond to read as the terminal event
          return (
            <g key={k}>
              <rect x={x - 5.5} y={parY - 5.5} width={11} height={11} rx={2} transform={`rotate(45 ${x} ${parY})`}
                    fill="var(--navy)" stroke="var(--navy)" strokeWidth="1.6" />
              <text x={x} y={parY - 13} fontSize="9.5" fontWeight={600} fill="var(--text-muted)" textAnchor="middle">{t('maturity_short')}</text>
            </g>
          )
        }
        return (
          <g key={k}>
            <circle cx={x} cy={parY} r={isAutocall ? 5 : 4} fill={isAutocall ? 'var(--accent)' : 'var(--surface)'}
                    stroke={isAutocall ? 'var(--accent)' : 'var(--border-strong)'} strokeWidth="1.8" />
            {showDotLabels && (
              <text x={x} y={parY - 12} fontSize="9" fill="var(--text-faint)" textAnchor="middle">P{k}</text>
            )}
          </g>
        )
      })}

      {/* footer caption */}
      <text x={X0 - 14} y={162} fontSize="10" fill="var(--text-faint)">
        {n} × {t(`freq_${terms.payment_freq}`)} · {pct(terms.coupon_pa, 1)} {t('coupon_pa').toLowerCase()}
        {terms.memory ? ` · ${t('memory').toLowerCase()}` : ''}
      </text>
    </svg>
  )
}
