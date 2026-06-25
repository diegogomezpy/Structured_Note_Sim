import { useI18n } from '../i18n/I18nProvider'
import { nObs, obsFractions, autocallSchedule, hasStepDown } from '../lib/terms'
import { pct } from '../lib/format'
import type { NoteTerms } from '../api/types'

const X0 = 34
const X1 = 496        // leaves a wide right gutter for the (longer in ES) barrier labels
const VIEW_W = 700
const Y_TOP = 22
const Y_BOT = 130
const DOMAIN = 1.18 // level mapped to the top of the chart

const mapY = (level: number) => Y_BOT - (Math.min(level, DOMAIN) / DOMAIN) * (Y_BOT - Y_TOP)
const mapX = (frac: number) => X0 + frac * (X1 - X0)

/** Barrier label: lowercase name + a bold value, right of the plot. */
function BarrierLabel({ y, color, name, value }: { y: number; color: string; name: string; value: string }) {
  return (
    <text x={X1 + 10} y={y + 3.2} fontSize="10">
      <tspan fill={color}>{name} </tspan>
      <tspan fill="var(--text)" fontWeight={600}>{value}</tspan>
    </text>
  )
}

/** Live schematic of the note: observation timeline + autocall window + the
    three barrier reference lines. Pure function of the terms — no simulation. */
export default function NoteTimeline({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  const n = nObs(terms)
  const fracs = obsFractions(terms)
  const start = Math.min(Math.max(terms.autocall_start_period, 1), n)

  const acLevel = terms.autocall_barrier
  const cpLevel = terms.coupon_barrier
  const kiLevel = terms.knock_in_barrier
  const lineY = mapY(acLevel)
  const acX = mapX((start - 1) / n) // autocall window opens just before period `start`

  const barriersEqual = Math.abs(cpLevel - kiLevel) < 1e-6
  const showDotLabels = n <= 8

  // Step-down autocall: draw the declining barrier as a stepped line (holds the
  // level between observations, drops at each).
  const stepped = hasStepDown(terms)
  const sched = stepped ? autocallSchedule(terms) : null
  const minAc = sched ? Math.min(...sched) : acLevel
  let stepPath = ''
  if (sched) {
    stepPath = `M ${X0} ${mapY(acLevel)}`
    fracs.forEach((f, i) => { stepPath += ` H ${mapX(f).toFixed(1)} V ${mapY(sched[i]).toFixed(1)}` })
  }

  // A small accent dot with a surface "halo" so it reads crisply over the band.
  const Dot = ({ x, r, fill, stroke }: { x: number; r: number; fill: string; stroke: string }) => (
    <>
      <circle cx={x} cy={lineY} r={r + 1.8} fill="var(--surface)" />
      <circle cx={x} cy={lineY} r={r} fill={fill} stroke={stroke} strokeWidth="1.6" />
    </>
  )

  return (
    <svg viewBox={`0 0 ${VIEW_W} 160`} width="100%" style={{ display: 'block', fontFamily: 'IBM Plex Sans, sans-serif' }}
         role="img" aria-label="Note structure timeline">
      {/* autocall window — soft band with a thin accent ledge along the top */}
      <rect x={acX} y={lineY - 17} width={X1 - acX} height={34} rx={9} fill="var(--accent-weak)" />
      <line x1={acX + 9} y1={lineY - 17} x2={X1} y2={lineY - 17} stroke="var(--accent)" strokeWidth="1" opacity="0.3" strokeLinecap="round" />
      <text x={acX + 9} y={lineY + 31} fontSize="9.5" fontWeight={600} letterSpacing="0.03em" fill="var(--accent-text)">
        {t('autocall_window')}
      </text>

      {/* barrier reference lines */}
      <line x1={X0} y1={mapY(cpLevel)} x2={X1} y2={mapY(cpLevel)}
            stroke="var(--accent)" strokeWidth="1.2" strokeDasharray="4 3" strokeLinecap="round" opacity="0.7" />
      {!barriersEqual && (
        <line x1={X0} y1={mapY(kiLevel)} x2={X1} y2={mapY(kiLevel)}
              stroke="var(--red)" strokeWidth="1.2" strokeDasharray="4 3" strokeLinecap="round" opacity="0.8" />
      )}

      {/* step-down autocall barrier (declining hurdle) */}
      {stepPath && (
        <path d={stepPath} fill="none" stroke="var(--text-muted)" strokeWidth="1.4"
              strokeDasharray="4 3" strokeLinecap="round" opacity="0.85" />
      )}

      {/* barrier labels (right) */}
      <BarrierLabel y={lineY} color="var(--text-muted)" name={t('autocall_barrier').toLowerCase()}
                    value={stepped ? `${pct(acLevel, 0)} → ${pct(minAc, 0)}` : pct(acLevel, 0)} />
      {barriersEqual ? (
        <BarrierLabel y={mapY(cpLevel)} color="var(--accent-text)"
                      name={`${t('coupon_barrier').toLowerCase()} · ${t('knock_in_barrier').toLowerCase()}`} value={pct(cpLevel, 0)} />
      ) : (
        <>
          <BarrierLabel y={mapY(cpLevel)} color="var(--accent-text)" name={t('coupon_barrier').toLowerCase()} value={pct(cpLevel, 0)} />
          <BarrierLabel y={mapY(kiLevel)} color="var(--red)" name={t('knock_in_barrier').toLowerCase()} value={pct(kiLevel, 0)} />
        </>
      )}

      {/* main observation axis */}
      <line x1={X0} y1={lineY} x2={X1} y2={lineY} stroke="var(--border-strong)" strokeWidth="1.5" strokeLinecap="round" />

      {/* issue */}
      <Dot x={X0} r={5} fill="var(--accent)" stroke="var(--accent)" />
      <text x={X0} y={lineY - 13} fontSize="10" fontWeight={500} fill="var(--text-muted)" textAnchor="middle">{t('issue')}</text>

      {/* observation dots */}
      {fracs.map((f, i) => {
        const k = i + 1
        const x = mapX(f)
        const isMat = k === n
        const isAutocall = k >= start
        const fill = isMat ? 'var(--navy)' : isAutocall ? 'var(--accent)' : 'var(--surface)'
        const stroke = isMat ? 'var(--navy)' : isAutocall ? 'var(--accent)' : 'var(--border-strong)'
        return (
          <g key={k}>
            <Dot x={x} r={isMat ? 5.5 : isAutocall ? 5 : 4.5} fill={fill} stroke={stroke} />
            {isMat && (
              <text x={x} y={lineY - 13} fontSize="10" fontWeight={500} fill="var(--text-muted)" textAnchor="middle">
                {t('maturity_short')}
              </text>
            )}
            {!isMat && showDotLabels && (
              <text x={x} y={lineY - 13} fontSize="9" fill="var(--text-faint)" textAnchor="middle">P{k}</text>
            )}
            {k === start && !isMat && (
              <text x={x} y={lineY + 27} fontSize="9.5" fill="var(--accent-text)" textAnchor="middle">★</text>
            )}
          </g>
        )
      })}

      {/* footer caption */}
      <text x={X0} y={152} fontSize="10" fill="var(--text-faint)">
        {n} × {t(`freq_${terms.payment_freq}`)} · {pct(terms.coupon_pa, 1)} {t('coupon_pa').toLowerCase()}
        {terms.memory ? ` · ${t('memory').toLowerCase()}` : ''}
      </text>
    </svg>
  )
}
