import { useId } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { nObs, obsFractions, autocallSchedule, hasStepDown } from '../lib/terms'
import { pct, pctTrim } from '../lib/format'
import { detectNoteType } from '../lib/noteType'
import ParticipationProfile from './ParticipationProfile'
import type { NoteTerms } from '../api/types'

// Payoff-zone schematic: a proper little chart with a worst-of level axis (y) and
// a time axis (x). Performance regions are shaded — green "capital protected"
// above the knock-in, red "capital at risk" below it — and the autocall window is
// drawn as a labelled band. Barrier reference lines carry their precise level in
// the right gutter. Pure function of the terms.
const VIEW_W = 760
const VIEW_H = 214
const X0 = 92          // plot left (room for y-axis tick labels)
const X1 = 548         // plot right (room for the gutter labels)
const Y_TOP = 26       // maps to DOMAIN (top of the level axis)
const Y_BOT = 178      // maps to 0%
const DOMAIN = 1.35    // top of the level axis
const LABEL_X = X1 + 14

const C_COUPON = '#3f8a6f'          /* secondary viridian */
const C_KNOCKIN = 'var(--red)'      /* claret */
const C_ONESTAR = 'var(--amber)'    /* ochre — the best-of rescue overlay */
const C_AUTOCALL = 'var(--accent-text)'

const PPY: Record<string, number> = { monthly: 12, quarterly: 4, 'semi-annual': 2, annual: 1 }

const mapY = (level: number) => Y_BOT - (Math.min(Math.max(level, 0), DOMAIN) / DOMAIN) * (Y_BOT - Y_TOP)
const mapX = (frac: number) => X0 + frac * (X1 - X0)

const fmtMonthYear = (iso: string) => { const d = new Date(`${iso}T00:00:00`); return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) }
const addYears = (iso: string, yrs: number) => { const d = new Date(`${iso}T00:00:00`); d.setDate(d.getDate() + Math.round(yrs * 365.25)); return d.toISOString().slice(0, 10) }
const tenorLabel = (years: number) => { const m = Math.round(years * 12); return m % 12 === 0 ? `${m / 12}y` : `${m}m` }
const yrTick = (y: number) => `${Number.isInteger(y) ? y : +y.toFixed(2)}y`

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

export default function NoteTimeline({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  const uid = useId().replace(/:/g, '')
  // A Participation note has no observation ladder — it's a maturity payoff, so
  // show its redemption profile instead of the barrier timeline.
  if (detectNoteType(terms) === 'participation') return <ParticipationProfile terms={terms} />
  const n = nObs(terms)
  const fracs = obsFractions(terms)
  const start = Math.min(Math.max(terms.autocall_start_period, 1), n)

  const acLevel = terms.autocall_barrier
  const cpLevel = terms.coupon_barrier
  const kiLevel = terms.knock_in_barrier
  const osLevel = terms.one_star_level
  const parY = mapY(1.0)
  const acY = mapY(acLevel)
  const kiY = mapY(kiLevel)
  const acX = mapX((start - 1) / n)
  const couponPer = terms.coupon_pa / (PPY[terms.payment_freq] ?? 4)

  const barriersEqual = Math.abs(cpLevel - kiLevel) < 1e-6
  const showCoupon = n <= 8 && couponPer > 0
  const showYrTicks = n <= 6

  // x-axis time: real dates when the note has an issue date, else the tenor
  const issueIso = terms.issue_date || null
  const issueDateLabel = issueIso ? fmtMonthYear(issueIso) : null
  const matDateLabel = issueIso ? fmtMonthYear(addYears(issueIso, terms.maturity)) : tenorLabel(terms.maturity)

  const stepped = hasStepDown(terms)
  const sched = stepped ? autocallSchedule(terms) : null
  const minAc = sched ? Math.min(...sched) : acLevel
  let stepPath = ''
  if (sched) {
    stepPath = `M ${X0} ${mapY(acLevel).toFixed(1)}`
    fracs.forEach((f, i) => { stepPath += ` H ${mapX(f).toFixed(1)} V ${mapY(sched[i]).toFixed(1)}` })
  }

  const acDesc = t(stepped ? 'diag_lgd_autocall_step' : 'diag_lgd_autocall', { lvl: stepped ? `${pctTrim(acLevel)} → ${pctTrim(minAc)}` : pctTrim(acLevel), p: `P${start}` })
  const cpDesc = t('diag_lgd_coupon', { cpn: pct(terms.coupon_pa, 1), lvl: pctTrim(cpLevel), mem: terms.memory ? t('diag_lgd_coupon_mem') : '' })
  const kiDesc = t('diag_lgd_knockin', { lvl: pctTrim(kiLevel) })

  // ── gutter labels: precise barrier level, de-collided, hover = full mechanic ──
  const entries: GutterEntry[] = [{
    target: acY, color: C_AUTOCALL, name: t('autocall_barrier'),
    value: stepped ? `${pctTrim(acLevel)} → ${pctTrim(minAc)}` : pctTrim(acLevel), desc: acDesc,
  }]
  if (barriersEqual) {
    entries.push({ target: kiY, color: C_COUPON, name: `${t('coupon_barrier')} · ${t('knock_in_barrier')}`, value: pctTrim(cpLevel), desc: `${cpDesc} ${kiDesc}` })
  } else {
    entries.push({ target: mapY(cpLevel), color: C_COUPON, name: t('coupon_barrier'), value: pctTrim(cpLevel), desc: cpDesc })
    entries.push({ target: kiY, color: C_KNOCKIN, name: t('knock_in_barrier'), value: pctTrim(kiLevel), desc: kiDesc })
  }
  if (osLevel != null) entries.push({ target: mapY(osLevel), color: C_ONESTAR, name: t('one_star'), value: pctTrim(osLevel), desc: t('diag_lgd_onestar', { lvl: pctTrim(osLevel) }) })
  const adjY = declutter(entries.map((e) => e.target), 14, Y_TOP + 2, Y_BOT)

  // y-axis ticks at round levels inside the domain
  const yTicks = [0, 0.5, 1.0].filter((l) => l <= DOMAIN)

  const Dot = ({ x, r, fill, stroke }: { x: number; r: number; fill: string; stroke: string }) => (
    <>
      <circle cx={x} cy={parY} r={r + 1.8} fill="var(--surface)" />
      <circle cx={x} cy={parY} r={r} fill={fill} stroke={stroke} strokeWidth="1.6" />
    </>
  )

  // labels for the shaded zones — placed in clear space, left-aligned inside the
  // plot. All three track their band so they move as barriers change: protected
  // sits between par and knock-in, at-risk between knock-in and the floor, and
  // the autocall caption centres in its (shrinking) band while staying clear of
  // the observation dots on the par line.
  const protTextY = (parY + kiY) / 2 + 3
  const riskTextY = (kiY + Y_BOT) / 2 + 3
  // The autocall caption centres in its band but must never dip into the row of
  // per-period coupon labels (which sit at parY-9); when no coupons are shown it
  // only needs to clear the observation dots.
  const windowFloor = showCoupon ? parY - 21 : parY - 9
  const windowTextY = Math.min((Y_TOP + acY) / 2 + 3, windowFloor)

  return (
    <div>
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} width="100%" style={{ display: 'block', fontFamily: 'var(--font-sans)' }}
           role="img" aria-label="Note payoff structure">
        <title>{t('diag_how_to_read')}</title>
        <defs>
          <clipPath id={`plot-${uid}`}><rect x={X0} y={Y_TOP} width={X1 - X0} height={Y_BOT - Y_TOP} /></clipPath>
        </defs>

        {/* payoff zones: protected (≥ knock-in) green, at-risk (< knock-in) red.
            Theme-aware tints (via --accent/--red) at a visible opacity so the
            green clearly fills the whole band down to the knock-in line and the
            at-risk band below it reads clearly reddish, in light and dark mode. */}
        <rect x={X0} y={Y_TOP} width={X1 - X0} height={Math.max(0, kiY - Y_TOP)} fill="var(--accent)" fillOpacity={0.12} />
        <rect x={X0} y={kiY} width={X1 - X0} height={Math.max(0, Y_BOT - kiY)} fill="var(--red)" fillOpacity={0.18} />

        {/* autocall window: above the autocall barrier, over the callable periods */}
        {start <= n && (
          <g clipPath={`url(#plot-${uid})`}>
            <rect x={acX} y={Y_TOP} width={X1 - acX} height={Math.max(0, acY - Y_TOP)} fill="var(--accent)" fillOpacity={0.10} />
            <line x1={acX} y1={Y_TOP} x2={acX} y2={acY} stroke="var(--accent-text)" strokeWidth="0.8" strokeDasharray="2 2" opacity="0.5" />
            <text x={(acX + X1) / 2} y={windowTextY} fontSize="9" fontWeight={600} fill="var(--accent-text)" textAnchor="middle" opacity="0.9">{t('diag_window')}</text>
          </g>
        )}

        {/* y gridlines + tick labels */}
        {yTicks.map((l) => (
          <g key={l}>
            <line x1={X0} y1={mapY(l)} x2={X1} y2={mapY(l)} stroke="var(--border)" strokeWidth="0.7" opacity="0.6" />
            <text x={X0 - 7} y={mapY(l) + 3} fontSize="8.5" className="mono" fill="var(--text-faint)" textAnchor="end">{pct(l, 0)}</text>
          </g>
        ))}

        {/* zone captions */}
        <text x={X0 + 7} y={protTextY} fontSize="9" fontWeight={600} fill="var(--accent)" opacity="0.85">{t('diag_zone_protected')}</text>
        {kiY < Y_BOT - 8 && (
          <text x={X0 + 7} y={riskTextY} fontSize="9" fontWeight={600} fill="var(--red)" opacity="0.8">{t('diag_zone_atrisk')}</text>
        )}

        {/* barrier reference lines (precise value floats in the gutter) */}
        {barriersEqual ? (
          <line x1={X0} y1={kiY} x2={X1} y2={kiY} stroke={C_KNOCKIN} strokeWidth="1.4" strokeDasharray="5 3" strokeLinecap="round" opacity="0.85" />
        ) : (
          <>
            <line x1={X0} y1={mapY(cpLevel)} x2={X1} y2={mapY(cpLevel)} stroke={C_COUPON} strokeWidth="1.3" strokeDasharray="5 3" strokeLinecap="round" opacity="0.85" />
            <line x1={X0} y1={kiY} x2={X1} y2={kiY} stroke={C_KNOCKIN} strokeWidth="1.4" strokeDasharray="5 3" strokeLinecap="round" opacity="0.9" />
          </>
        )}
        {osLevel != null && (
          <line x1={X0} y1={mapY(osLevel)} x2={X1} y2={mapY(osLevel)} stroke={C_ONESTAR} strokeWidth="1.3" strokeDasharray="5 3" strokeLinecap="round" opacity="0.8" />
        )}
        {stepPath && (
          <path d={stepPath} fill="none" stroke="var(--accent-text)" strokeWidth="1.4" strokeDasharray="4 3" strokeLinecap="round" opacity="0.85" />
        )}

        {/* gutter labels: neutral leader + anchor dot (clearly not a barrier); hover for detail.
            A long label (e.g. the combined coupon·knock-in name in Spanish with a
            3-decimal value) is condensed with textLength so it never spills past
            the SVG's right edge and gets clipped. */}
        {entries.map((e, i) => {
          const avail = VIEW_W - LABEL_X - 3
          const fit = (e.name.length + e.value.length + 1) * 5.2 > avail
            ? { textLength: avail, lengthAdjust: 'spacingAndGlyphs' as const } : {}
          return (
            <g key={i}>
              <title>{e.desc}</title>
              <circle cx={X1 + 3} cy={e.target} r={1.6} fill="var(--text-faint)" />
              <path d={`M ${X1 + 3} ${e.target.toFixed(1)} L ${LABEL_X - 6} ${adjY[i].toFixed(1)}`}
                    fill="none" stroke="var(--text-faint)" strokeWidth="0.9" />
              <text x={LABEL_X} y={adjY[i] + 3.2} fontSize="10" {...fit}>
                <tspan fill={e.color}>{e.name} </tspan>
                <tspan fill="var(--text)" fontWeight={600}>{e.value}</tspan>
              </text>
            </g>
          )
        })}

        {/* axes — extended past the data with arrowheads so the chart doesn't end abruptly */}
        <line x1={X0} y1={Y_BOT} x2={X0} y2={Y_TOP - 7} stroke="var(--border-strong)" strokeWidth="1.2" />
        <path d={`M ${X0 - 3} ${Y_TOP - 4} L ${X0} ${Y_TOP - 8} L ${X0 + 3} ${Y_TOP - 4} Z`} fill="var(--border-strong)" />
        <line x1={X0} y1={Y_BOT} x2={X1 + 8} y2={Y_BOT} stroke="var(--border-strong)" strokeWidth="1.2" />
        <path d={`M ${X1 + 5} ${Y_BOT - 3} L ${X1 + 9} ${Y_BOT} L ${X1 + 5} ${Y_BOT + 3} Z`} fill="var(--border-strong)" />
        <text x={X0 - 9} y={Y_TOP - 9} fontSize="8.5" fontWeight={600} fill="var(--text-faint)" textAnchor="start">{t('diag_axis_level')}</text>
        {/* end captions: issue / maturity word, with the real date (or tenor) below */}
        <text x={X0} y={Y_BOT + 13} fontSize="9.5" fontWeight={500} fill="var(--text-muted)" textAnchor="middle">{t('issue')}</text>
        {issueDateLabel && <text x={X0} y={Y_BOT + 23} fontSize="8" className="mono" fill="var(--text-faint)" textAnchor="middle">{issueDateLabel}</text>}
        <text x={X1} y={Y_BOT + 13} fontSize="9.5" fontWeight={500} fill="var(--text-muted)" textAnchor="middle">{t('maturity_short')}</text>
        <text x={X1} y={Y_BOT + 23} fontSize="8" className="mono" fontWeight={600} fill="var(--text-muted)" textAnchor="middle">{matDateLabel}</text>

        {/* observation nodes on the par line + per-period coupon above them */}
        {fracs.map((f, i) => {
          const k = i + 1
          const x = mapX(f)
          const isMat = k === n
          const isAutocall = k >= start
          const fill = isMat ? 'var(--navy)' : isAutocall ? 'var(--accent)' : 'var(--surface)'
          const stroke = isMat ? 'var(--navy)' : isAutocall ? 'var(--accent)' : 'var(--border-strong)'
          return (
            <g key={k}>
              <line x1={x} y1={parY} x2={x} y2={Y_BOT} stroke="var(--border)" strokeWidth="0.7" strokeDasharray="2 3" opacity="0.5" />
              <Dot x={x} r={isMat ? 5 : isAutocall ? 4.5 : 4} fill={fill} stroke={stroke} />
              {showCoupon && (
                <text x={x} y={parY - 9} fontSize="8" className="mono" fill={C_COUPON} textAnchor="middle">+{pct(couponPer, 2)}</text>
              )}
              {showYrTicks && !isMat && (
                <text x={x} y={Y_BOT + 13} fontSize="7.5" className="mono" fill="var(--text-faint)" textAnchor="middle">{yrTick(f * terms.maturity)}</text>
              )}
            </g>
          )
        })}

        {/* issue marker on the par line */}
        <Dot x={X0} r={4.5} fill="var(--accent)" stroke="var(--accent)" />
      </svg>
    </div>
  )
}
