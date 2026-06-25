import { useId } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { nObs, obsFractions, autocallSchedule, hasStepDown } from '../lib/terms'
import { pct } from '../lib/format'
import type { NoteTerms } from '../api/types'

const VIEW_W = 720
const X0 = 40
const X1 = 470        // axis right end — leaves a gutter for the floating labels
const VIEW_H = 118
const Y_TOP = 30
const Y_BOT = 104
const DOMAIN = 1.30   // level mapped to the top of the plot
const LABEL_X = X1 + 30

// Distinct, colour-matched so each dashed barrier and its floating label agree.
const C_COUPON = '#0891b2'
const C_KNOCKIN = 'var(--red)'
const C_ONESTAR = '#16a34a'
const C_AUTOCALL = 'var(--accent-text)'

const PPY: Record<string, number> = { monthly: 12, quarterly: 4, 'semi-annual': 2, annual: 1 }

const mapY = (level: number) => Y_BOT - (Math.min(Math.max(level, 0), DOMAIN) / DOMAIN) * (Y_BOT - Y_TOP)
const mapX = (frac: number) => X0 + frac * (X1 - X0)

/** Greedily separate label y-positions by at least `gap`, kept inside [minY,maxY],
    returned in the original order — so each label clears its neighbours. */
function declutter(ys: number[], gap: number, minY: number, maxY: number): number[] {
  const idx = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y)
  for (let k = 1; k < idx.length; k++) if (idx[k].y < idx[k - 1].y + gap) idx[k].y = idx[k - 1].y + gap
  const over = (idx[idx.length - 1]?.y ?? 0) - maxY
  if (over > 0) idx.forEach((o) => { o.y -= over })
  const under = minY - (idx[0]?.y ?? minY)
  if (under > 0) idx.forEach((o) => { o.y += under })
  const out = ys.slice()
  idx.forEach((o) => { out[o.i] = o.y })
  return out
}

interface GutterEntry { target: number; color: string; name: string; value: string; desc: string }

/** Live schematic of the note: observation timeline + autocall window + the
    barrier reference lines, with floating value labels (joined to each line by a
    neutral pointer; hover for the full mechanic). Pure function of the terms. */
export default function NoteTimeline({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  const uid = useId().replace(/:/g, '')
  const n = nObs(terms)
  const fracs = obsFractions(terms)
  const start = Math.min(Math.max(terms.autocall_start_period, 1), n)

  const acLevel = terms.autocall_barrier
  const cpLevel = terms.coupon_barrier
  const kiLevel = terms.knock_in_barrier
  const osLevel = terms.one_star_level
  const lineY = mapY(acLevel)
  const acX = mapX((start - 1) / n)
  const couponPer = terms.coupon_pa / (PPY[terms.payment_freq] ?? 4)

  const barriersEqual = Math.abs(cpLevel - kiLevel) < 1e-6
  const showCoupon = n <= 8 && couponPer > 0

  const stepped = hasStepDown(terms)
  const sched = stepped ? autocallSchedule(terms) : null
  const minAc = sched ? Math.min(...sched) : acLevel
  let stepPath = ''
  if (sched) {
    stepPath = `M ${X0} ${mapY(acLevel).toFixed(1)}`
    fracs.forEach((f, i) => { stepPath += ` H ${mapX(f).toFixed(1)} V ${mapY(sched[i]).toFixed(1)}` })
  }

  const acDesc = t(stepped ? 'diag_lgd_autocall_step' : 'diag_lgd_autocall', { lvl: stepped ? `${pct(acLevel, 0)} → ${pct(minAc, 0)}` : pct(acLevel, 0), p: `P${start}` })
  const cpDesc = t('diag_lgd_coupon', { cpn: pct(terms.coupon_pa, 1), lvl: pct(cpLevel, 0), mem: terms.memory ? t('diag_lgd_coupon_mem') : '' })
  const kiDesc = t('diag_lgd_knockin', { lvl: pct(kiLevel, 0) })

  // ── floating gutter labels (de-collided; hover = full mechanic) ──────────────
  const entries: GutterEntry[] = [{
    target: lineY, color: C_AUTOCALL, name: t('autocall_barrier'),
    value: stepped ? `${pct(acLevel, 0)} → ${pct(minAc, 0)}` : pct(acLevel, 0), desc: acDesc,
  }]
  if (barriersEqual) {
    entries.push({ target: mapY(cpLevel), color: C_COUPON, name: `${t('coupon_barrier')} · ${t('knock_in_barrier')}`, value: pct(cpLevel, 0), desc: `${cpDesc} ${kiDesc}` })
  } else {
    entries.push({ target: mapY(cpLevel), color: C_COUPON, name: t('coupon_barrier'), value: pct(cpLevel, 0), desc: cpDesc })
    entries.push({ target: mapY(kiLevel), color: C_KNOCKIN, name: t('knock_in_barrier'), value: pct(kiLevel, 0), desc: kiDesc })
  }
  if (osLevel != null) entries.push({ target: mapY(osLevel), color: C_ONESTAR, name: t('one_star'), value: pct(osLevel, 0), desc: t('diag_lgd_onestar', { lvl: pct(osLevel, 0) }) })
  const adjY = declutter(entries.map((e) => e.target), 15, Y_TOP + 2, Y_BOT + 8)

  const couponNote = couponPer > 0 ? ` · +${pct(couponPer, 2)}/${t('per_period')}` : ''
  const summary = `${n} × ${t(`freq_${terms.payment_freq}`)} · ${pct(terms.coupon_pa, 1)} ${t('coupon_pa').toLowerCase()}${couponNote}${terms.memory ? ` · ${t('memory').toLowerCase()}` : ''}`

  const Dot = ({ x, r, fill, stroke }: { x: number; r: number; fill: string; stroke: string }) => (
    <>
      <circle cx={x} cy={lineY} r={r + 1.8} fill="var(--surface)" />
      <circle cx={x} cy={lineY} r={r} fill={fill} stroke={stroke} strokeWidth="1.6" />
    </>
  )

  return (
    <div>
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} width="100%" style={{ display: 'block', fontFamily: 'IBM Plex Sans, sans-serif' }}
           role="img" aria-label="Note structure timeline">
        {/* autocall window band */}
        <rect x={acX} y={lineY - 9} width={X1 - acX} height={18} rx={6} fill="var(--accent-weak)" />

        {/* barrier reference lines (values float in the gutter) */}
        {barriersEqual ? (
          <line x1={X0} y1={mapY(cpLevel)} x2={X1} y2={mapY(cpLevel)} stroke={C_COUPON} strokeWidth="1.3" strokeDasharray="5 3" strokeLinecap="round" opacity="0.85" />
        ) : (
          <>
            <line x1={X0} y1={mapY(cpLevel)} x2={X1} y2={mapY(cpLevel)} stroke={C_COUPON} strokeWidth="1.3" strokeDasharray="5 3" strokeLinecap="round" opacity="0.85" />
            <line x1={X0} y1={mapY(kiLevel)} x2={X1} y2={mapY(kiLevel)} stroke={C_KNOCKIN} strokeWidth="1.3" strokeDasharray="5 3" strokeLinecap="round" opacity="0.85" />
          </>
        )}
        {osLevel != null && (
          <line x1={X0} y1={mapY(osLevel)} x2={X1} y2={mapY(osLevel)} stroke={C_ONESTAR} strokeWidth="1.3" strokeDasharray="5 3" strokeLinecap="round" opacity="0.8" />
        )}
        {stepPath && (
          <path d={stepPath} fill="none" stroke="var(--text-muted)" strokeWidth="1.4" strokeDasharray="4 3" strokeLinecap="round" opacity="0.85" />
        )}

        {/* floating labels: neutral solid leader + anchor dot (clearly not a barrier); hover for detail */}
        {entries.map((e, i) => (
          <g key={i}>
            <title>{e.desc}</title>
            <circle cx={X1 + 3} cy={e.target} r={1.6} fill="var(--text-faint)" />
            <path d={`M ${X1 + 3} ${e.target.toFixed(1)} L ${LABEL_X - 6} ${adjY[i].toFixed(1)}`}
                  fill="none" stroke="var(--text-faint)" strokeWidth="0.9" />
            <text x={LABEL_X} y={adjY[i] + 3.2} fontSize="10.5">
              <tspan fill={e.color}>{e.name} </tspan>
              <tspan fill="var(--text)" fontWeight={600}>{e.value}</tspan>
            </text>
          </g>
        ))}

        {/* main observation axis (sits at the autocall level) */}
        <line x1={X0} y1={lineY} x2={X1} y2={lineY} stroke="var(--border-strong)" strokeWidth="1.5" strokeLinecap="round" />

        {/* issue */}
        <Dot x={X0} r={5} fill="var(--accent)" stroke="var(--accent)" />
        <text x={X0} y={lineY - 24} fontSize="10" fontWeight={500} fill="var(--text-muted)" textAnchor="middle">{t('issue')}</text>

        {/* observation nodes + per-period coupon (placed ABOVE the axis, clear of the barriers below) */}
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
                <text x={x + 2} y={lineY - 24} fontSize="10" fontWeight={500} fill="var(--text-muted)" textAnchor="end">{t('maturity_short')}</text>
              )}
              {showCoupon && (
                <text x={x} y={lineY - 13} fontSize="8" className="mono" fill={C_COUPON} textAnchor="middle">+{pct(couponPer, 2)}</text>
              )}
            </g>
          )
        })}
      </svg>

      <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 6, paddingTop: 8, borderTop: '1px solid var(--border)' }}>{summary}</div>
    </div>
  )
}
