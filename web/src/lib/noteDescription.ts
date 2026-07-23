/* Systematic, terms-driven note description — the "Esta Inversión (la Nota)…"
   blurb that fills itself out from the note's terms.

   Mirror of the Python source in `core/note_description.py` (used by the PDF
   report). Keep the two templates in sync if either changes. */
import type { NoteTerms } from '../api/types'
import type { Lang } from '../i18n/strings'
import { nObs } from './terms'

/** Tenors are quoted in months throughout the app, prose included. */
function duration(maturity: number, lang: Lang): string {
  const months = Math.round(maturity * 12)
  if (lang === 'es') return months === 1 ? '1 mes' : `${months} meses`
  return months === 1 ? '1 month' : `${months} months`
}

function freqWord(freq: NoteTerms['payment_freq'], lang: Lang): string {
  const es: Record<string, string> = { monthly: 'Mensual', quarterly: 'Trimestral', 'semi-annual': 'Semestral', annual: 'Anual' }
  const en: Record<string, string> = { monthly: 'monthly', quarterly: 'quarterly', 'semi-annual': 'semi-annual', annual: 'annual' }
  return (lang === 'es' ? es : en)[freq] ?? (lang === 'es' ? 'Trimestral' : 'quarterly')
}

function joinNames(names: string[], lang: Lang): string {
  if (names.length === 0) return ''
  if (names.length === 1) return names[0]
  const conj = lang === 'es' ? 'y' : 'and'
  return `${names.slice(0, -1).join(', ')} ${conj} ${names[names.length - 1]}`
}

const p2 = (x: number) => `${parseFloat((x * 100).toFixed(2))}%`

/** How a basket rule reads in prose. */
function basketWord(kind: string | undefined, lang: Lang, multi: boolean): string {
  if (!multi) return lang === 'es' ? 'el Subyacente' : 'the Underlying'
  const es: Record<string, string> = { worst_of: 'el peor de los Subyacentes', best_of: 'el mejor de los Subyacentes', average: 'el promedio de los Subyacentes' }
  const en: Record<string, string> = { worst_of: 'the worst-performing Underlying', best_of: 'the best-performing Underlying', average: 'the average of the Underlyings' }
  const m = lang === 'es' ? es : en
  return m[kind ?? 'worst_of'] ?? m.worst_of
}

/** Per-observation autocall barrier levels (mirrors autocallSchedule in terms.ts). */
function acSchedule(t: NoteTerms, n: number): number[] {
  const levels = Array.from({ length: n }, () => t.autocall_barrier)
  const step = t.autocall_step_down ?? 0
  if (step > 0) {
    for (let j = t.autocall_start_period; j <= n; j++) {
      let lvl = t.autocall_barrier - step * (j - t.autocall_start_period)
      if (t.autocall_floor != null) lvl = Math.max(lvl, t.autocall_floor)
      levels[j - 1] = lvl
    }
  }
  return levels
}

/** One short paragraph per ACTIVE feature: what the mechanic IS, then this
    note's numbers. Mirrors _phoenix_features in core/note_description.py. */
function phoenixFeatures(terms: NoteTerms, lang: Lang, multi: boolean, nObsCount: number): string[] {
  const out: string[] = []
  const es = lang === 'es'

  if (multi) {
    const cw = basketWord(terms.coupon_basket, lang, true)
    const aw = basketWord(terms.autocall_basket, lang, true)
    if (terms.coupon_basket === terms.autocall_basket) {
      out.push(es
        ? `Cesta. Todas las condiciones se miden sobre ${cw}: basta con que ese Subyacente incumpla un nivel para que la condición no se cumpla, por muy bien que se comporten los demás.`
        : `Basket. Every condition is measured on ${cw}: it only takes that one Underlying to miss a level for the condition to fail, however well the others perform.`)
    } else {
      out.push(es
        ? `Cesta. El cupón se mide sobre ${cw} y la cancelación anticipada sobre ${aw}.`
        : `Basket. The coupon is measured on ${cw}, while early redemption is measured on ${aw}.`)
    }
  }

  const step = terms.autocall_step_down ?? 0
  if (step > 0) {
    const sched = acSchedule(terms, nObsCount)
    const first = sched[Math.max(0, terms.autocall_start_period - 1)]
    const last = sched[sched.length - 1]
    const floor = terms.autocall_floor
    if (es) {
      let txt = `Step-down (barrera decreciente). La barrera de cancelación anticipada no es fija: empieza en el ${p2(first)} en la primera observación con posibilidad de cancelación y baja ${p2(step)} en cada observación posterior`
      txt += floor != null ? `, con un suelo del ${p2(floor)}.` : '.'
      txt += ` Al final del plazo la Nota puede cancelarse con el Subyacente en el ${p2(last)}, de modo que cuanto más dura la Nota, más fácil le resulta cancelarse.`
      out.push(txt)
    } else {
      let txt = `Step-down (declining barrier). The early-redemption barrier is not fixed: it starts at ${p2(first)} on the first callable observation and falls ${p2(step)} at each observation thereafter`
      txt += floor != null ? `, subject to a ${p2(floor)} floor.` : '.'
      txt += ` By the end of the term the Note can redeem with the Underlying at ${p2(last)}, so the longer the Note runs the easier it becomes for it to redeem.`
      out.push(txt)
    }
  }

  if (terms.coupon_at_autocall_only) {
    out.push(es
      ? 'Prima a la cancelación. La Nota no paga cupones periódicos: la prima se acumula en cada observación y se abona en un único pago cuando la Nota se cancela anticipadamente o vence.'
      : 'Premium at redemption. The Note pays no periodic coupons: the premium accrues at each observation and is paid as a single lump sum when the Note redeems early or matures.')
  }

  const lvl = terms.one_star_level
  if (lvl != null && multi) {
    const acts: string[] = []
    if (terms.one_star_coupon) acts.push(es ? 'pagar el cupón' : 'pay the coupon')
    if (terms.one_star_autocall) acts.push(es ? 'activar la cancelación anticipada' : 'trigger early redemption')
    if (es) {
      let txt = `One Star. Una excepción a la regla del peor de: en lugar de exigir que TODOS los Subyacentes cumplan, basta con que UNO SOLO esté en o por encima del ${p2(lvl)} de su nivel inicial. `
      txt += acts.length
        ? `Ese único Subyacente basta para ${acts.join(' y ')}, y para devolver el capital a la par al vencimiento aunque el peor haya perforado la Barrera de Knock-in.`
        : 'Se aplica únicamente a la redención final: devuelve el capital a la par al vencimiento aunque el peor Subyacente haya perforado la Barrera de Knock-in, sin afectar al cupón ni a la cancelación anticipada.'
      out.push(txt)
    } else {
      let txt = `One Star. An exception to the worst-of rule: instead of requiring EVERY Underlying to qualify, a SINGLE Underlying at or above ${p2(lvl)} of its initial level is enough. `
      txt += acts.length
        ? `That one Underlying suffices to ${acts.join(' and ')}, and to repay capital at par at maturity even if the worst has breached the Knock-in Barrier.`
        : 'It applies to final redemption only: it repays capital at par at maturity even if the worst Underlying has breached the Knock-in Barrier, without affecting the coupon or early-redemption conditions.'
      out.push(txt)
    }
  }

  if (terms.zenith) {
    const rate = p2(terms.participation_rate ?? 1)
    const cap = terms.upside_cap
    const wof = basketWord('worst_of', lang, multi)
    out.push(es
      ? `Zenith. Convierte una Nota de ingresos en una que además participa de la subida. Siempre que la Nota se cancele anticipadamente, o venza con el Nivel Final en o por encima de su nivel inicial, el inversor recibe —además del cupón y del capital— una participación del ${rate} en la revalorización de ${wof} (${cap == null ? 'sin límite' : `limitada a +${p2(cap)}`}). Si la Nota termina por debajo de la par, Zenith no aplica y rige la protección habitual.`
      : `Zenith. Turns an income Note into one that also participates in the upside. Whenever the Note redeems early, or matures with the Final Level at or above its initial level, the investor receives — on top of the coupon and capital — ${rate} participation in the rise of ${wof} (${cap == null ? 'uncapped' : `capped at +${p2(cap)}`}). If the Note finishes below par, Zenith does not apply and the usual protection governs.`)
  }

  const pp = terms.principal_protection
  if (pp != null && Math.abs(pp - 1) > 1e-9) {
    out.push(es
      ? `Protección del principal. Si la Nota llega a vencimiento sin haber perforado la Barrera de Knock-in, el capital se redime al ${p2(pp)} en lugar de la par.`
      : `Principal protection. If the Note reaches maturity without breaching the Knock-in Barrier, capital redeems at ${p2(pp)} rather than at par.`)
  }

  return out
}

/** Prose for a Participation Note (a maturity payoff profile, no coupons). */
function participationDescription(terms: NoteTerms, lang: Lang, joined: string, multi: boolean): string {
  const dur = duration(terms.maturity, lang)
  const prot = terms.protection_level ?? 0, rate = terms.participation_rate ?? 0
  const strike = terms.participation_strike ?? 1, cap = terms.upside_cap
  const pd = terms.participation_downside ?? 'full', pu = terms.participation_upside ?? 'linear'
  const es = lang === 'es'
  const subj = es ? (multi ? 'los Subyacentes' : 'el Subyacente') : (multi ? 'the Underlyings' : 'the Underlying')
  const bword = es
    ? ({ worst_of: 'el peor rendimiento', best_of: 'el mejor rendimiento', average: 'el rendimiento promedio' }[terms.participation_basket ?? 'worst_of'])
    : ({ worst_of: 'the worst-performing', best_of: 'the best-performing', average: 'the average' }[terms.participation_basket ?? 'worst_of'])
  if (terms.participation_periodic) {
    const freq = freqWord(terms.payment_freq, lang)
    const pcap = terms.period_cap
    const capph = pcap != null ? (es ? ` (limitada al ${p2(pcap)} por período)` : ` (capped at ${p2(pcap)} per period)`) : ''
    return es
      ? `Esta Nota está vinculada a ${bword} de ${joined}, ${subj}, con una duración de ${dur}. En cada fecha de reinicio ${freq} paga el ${p2(rate)} de la subida de ese período${capph}; los períodos a la baja no pagan nada y el strike se reinicia. El capital está protegido al ${p2(Math.min(prot, 1))} al vencimiento.`
      : `This Note is linked to ${bword} of ${joined}, ${subj}, over ${dur}. At each ${freq} reset date it pays ${p2(rate)} of that period's rise${capph}; down periods pay nothing and the strike resets. Capital is protected at ${p2(Math.min(prot, 1))} at maturity.`
  }
  const head = es
    ? `Esta Nota está vinculada a ${bword} de ${joined}, ${subj}, con una duración máxima de ${dur}. No paga cupones periódicos; la redención al vencimiento depende del nivel final. `
    : `This Note is linked to ${bword} of ${joined}, ${subj}, over a maximum term of ${dur}. It pays no periodic coupons; redemption at maturity depends on the final level. `
  if (pd === 'bear') {
    const capTxt = cap != null ? (es ? ` La redención está limitada al ${p2(1 + cap)}.` : ` Redemption is capped at ${p2(1 + cap)}.`) : ''
    return head + (es
      ? `La Nota participa al ${p2(rate)} de la caída por debajo del strike del ${p2(strike)}, con un suelo del ${p2(prot)}; por encima del strike el capital se redime al ${p2(prot)}.${capTxt}`
      : `The Note participates at ${p2(rate)} of the fall below the ${p2(strike)} strike, floored at ${p2(prot)}; above the strike capital is redeemed at ${p2(prot)}.${capTxt}`)
  }
  let up: string
  if (pu === 'digital') up = es
    ? `Si el nivel final está en o por encima del strike del ${p2(strike)}, la Nota paga un importe fijo del ${p2(1 + (terms.digital_payout ?? 0))}.`
    : `If the final level is at or above the ${p2(strike)} strike, the Note pays a fixed ${p2(1 + (terms.digital_payout ?? 0))}.`
  else if (pu === 'shark_fin') up = es
    ? `Por encima del strike del ${p2(strike)} se participa al ${p2(rate)} de la subida hasta el knock-out del ${p2(terms.knockout_level ?? 0)}; si el nivel final supera el knock-out, la Nota se redime al ${p2(terms.knockout_payout ?? 1)}.`
    : `Above the ${p2(strike)} strike you participate at ${p2(rate)} of the rise up to the ${p2(terms.knockout_level ?? 0)} knock-out; if the final level is above the knock-out, the Note redeems at ${p2(terms.knockout_payout ?? 1)}.`
  else up = es
    ? `Por encima del strike del ${p2(strike)} se participa al ${p2(rate)} de la subida${cap != null ? `, con un tope del ${p2(1 + cap)}.` : '.'}`
    : `Above the ${p2(strike)} strike you participate at ${p2(rate)} of the rise${cap != null ? `, capped at ${p2(1 + cap)}.` : '.'}`
  const dn = {
    full: es ? ` Si el nivel final está por debajo del strike, el capital se redime al ${p2(Math.min(prot, 1))}.` : ` If the final level is below the strike, capital is redeemed at ${p2(Math.min(prot, 1))}.`,
    buffer: es ? ` El capital está protegido hasta el nivel de protección del ${p2(prot)}; por debajo, las pérdidas son 1:1.` : ` Capital is protected down to the ${p2(prot)} protection level; below it, losses apply one-for-one.`,
    airbag: es ? ` El capital está protegido hasta la barrera del ${p2(prot)}; por debajo, la redención es apalancada (nivel final dividido por la barrera).` : ` Capital is protected down to the ${p2(prot)} barrier; below it, redemption is geared (final level divided by the barrier).`,
  }[pd] ?? ''
  return head + up + dn
}

/** Generate the prose note description from `terms` (en/es). */
export function noteDescription(terms: NoteTerms, lang: Lang): string {
  const names = Object.values(terms.tickers ?? {})
  const multi = names.length > 1
  if (terms.note_type === 'participation') return participationDescription(terms, lang, joinNames(names, lang), multi)
  const freq = freqWord(terms.payment_freq, lang)
  const dur = duration(terms.maturity, lang)
  const cpn = p2(terms.coupon_pa)
  const cb = p2(terms.coupon_barrier)
  const ki = p2(terms.knock_in_barrier)
  const start = Math.max(1, Math.round(terms.autocall_start_period))
  const nObsCount = nObs(terms)
  const joined = joinNames(names, lang)

  if (lang === 'es') {
    const each = multi ? 'cada Subyacente' : 'el Subyacente'
    const anyu = multi ? 'alguno de los Subyacentes' : 'el Subyacente'
    const subj = multi ? 'los Subyacentes' : 'el Subyacente'
    let s =
      `Esta Inversión (la Nota) genera unos Ingresos con posibilidad de cancelación anticipada y está ` +
      `vinculada al rendimiento de ${joined}, ${subj}. Tiene una duración máxima de ${dur} y genera un ` +
      `Ingreso equivalente al ${cpn} p.a., siempre y cuando el precio de cierre de ${each} sea igual o ` +
      `superior al ${cb} de su nivel de Strike en cada observación ${freq}. Si el precio de cierre de ${anyu} ` +
      `se encuentra por debajo del ${cb} de su nivel de Strike en cualquier Fecha de Observación ${freq} el ` +
      `cupón de dicha observación ${freq} no es pagado. `
    if (terms.memory)
      s += `Sin embargo, los cupones no pagados pueden ser pagados en una futura observación ${freq} si el precio ` +
        `de cierre de ${each} se encuentra por encima de la Barrera de Cupón en la Fecha de Observación ${freq} ` +
        `relevante (efecto memoria). `
    s += `La Nota tiene también la posibilidad de vencer anticipadamente a partir de la observación ${start} y en ` +
      `cada Fecha de Observación ${freq} en adelante, siempre y cuando el precio de cierre de ${each} sea igual o ` +
      `superior al nivel de Autocall de dicha Fecha de Observación ${freq}. `
    s += `El Capital se encuentra en riesgo si la Nota no ha vencido anticipadamente y el Nivel Final de ${anyu} se ` +
      `encuentra por debajo del ${ki} de su nivel de Strike inicial en la Fecha de Observación Final.`
    return [s, ...phoenixFeatures(terms, lang, multi, nObsCount)].join('\n\n')
  }

  const each = multi ? 'each Underlying' : 'the Underlying'
  const anyu = multi ? 'any Underlying' : 'the Underlying'
  const subj = multi ? 'the Underlyings' : 'the Underlying'
  let s =
    `This Investment (the Note) generates Income with the possibility of early redemption and is linked to the ` +
    `performance of ${joined}, ${subj}. It has a maximum duration of ${dur} and pays Income equivalent to ${cpn} ` +
    `p.a., provided that the closing price of ${each} is at or above ${cb} of its Strike level on each ${freq} ` +
    `observation. If the closing price of ${anyu} is below ${cb} of its Strike level on any ${freq} Observation ` +
    `Date, the coupon for that ${freq} observation is not paid. `
  if (terms.memory)
    s += `However, unpaid coupons may be paid on a future ${freq} observation if the closing price of ${each} is ` +
      `above the Coupon Barrier on the relevant ${freq} Observation Date (memory effect). `
  s += `The Note may also redeem early from observation ${start} and on each ${freq} Observation Date thereafter, ` +
    `provided that the closing price of ${each} is at or above the Autocall level of that ${freq} Observation Date. `
  s += `Capital is at risk if the Note has not redeemed early and the Final Level of ${anyu} is below ${ki} of its ` +
    `initial Strike level on the Final Observation Date.`
  return [s, ...phoenixFeatures(terms, lang, multi, nObsCount)].join('\n\n')
}
