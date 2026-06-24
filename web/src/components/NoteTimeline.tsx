import { useI18n } from '../i18n/I18nProvider'
import { nObs, obsFractions } from '../lib/terms'
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

  return (
    <svg viewBox={`0 0 ${VIEW_W} 160`} width="100%" style={{ display: 'block', fontFamily: 'IBM Plex Sans, sans-serif' }}
         role="img" aria-label="Note structure timeline">
      {/* autocall window */}
      <rect x={acX} y={lineY - 16} width={X1 - acX} height={32} rx={6}
            fill="var(--accent-weak)" />
      <text x={acX + 6} y={lineY + 30} fontSize="10" fill="var(--accent-text)">
        {t('autocall_window')}
      </text>

      {/* barrier lines */}
      <line x1={X0} y1={mapY(cpLevel)} x2={X1} y2={mapY(cpLevel)}
            stroke="var(--accent)" strokeWidth="1" strokeDasharray="3 3" opacity="0.65" />
      {!barriersEqual && (
        <line x1={X0} y1={mapY(kiLevel)} x2={X1} y2={mapY(kiLevel)}
              stroke="var(--red)" strokeWidth="1" strokeDasharray="3 3" opacity="0.75" />
      )}

      {/* barrier labels (right) */}
      <text x={X1 + 8} y={lineY + 3} fontSize="10" fill="var(--text-muted)">
        {t('autocall_barrier').toLowerCase()} {pct(acLevel, 0)}
      </text>
      {barriersEqual ? (
        <text x={X1 + 8} y={mapY(cpLevel) + 3} fontSize="10" fill="var(--accent-text)">
          {t('coupon_barrier').toLowerCase()} · {t('knock_in_barrier').toLowerCase()} {pct(cpLevel, 0)}
        </text>
      ) : (
        <>
          <text x={X1 + 8} y={mapY(cpLevel) + 3} fontSize="10" fill="var(--accent-text)">
            {t('coupon_barrier').toLowerCase()} {pct(cpLevel, 0)}
          </text>
          <text x={X1 + 8} y={mapY(kiLevel) + 3} fontSize="10" fill="var(--red)">
            {t('knock_in_barrier').toLowerCase()} {pct(kiLevel, 0)}
          </text>
        </>
      )}

      {/* main observation axis */}
      <line x1={X0} y1={lineY} x2={X1} y2={lineY} stroke="var(--border-strong)" strokeWidth="1.5" />

      {/* issue */}
      <circle cx={X0} cy={lineY} r={5} fill="var(--accent)" />
      <text x={X0} y={lineY - 12} fontSize="10" fill="var(--text-muted)" textAnchor="middle">{t('issue')}</text>

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
            <circle cx={x} cy={lineY} r={isMat ? 5.5 : isAutocall ? 5 : 4.5}
                    fill={fill} stroke={stroke} strokeWidth="1.6" />
            {isMat && (
              <text x={x} y={lineY - 12} fontSize="10" fill="var(--text-muted)" textAnchor="middle">
                {t('maturity_short')}
              </text>
            )}
            {!isMat && showDotLabels && (
              <text x={x} y={lineY - 12} fontSize="9" fill="var(--text-faint)" textAnchor="middle">P{k}</text>
            )}
            {k === start && !isMat && (
              <text x={x} y={lineY + 26} fontSize="9" fill="var(--accent-text)" textAnchor="middle">★</text>
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
