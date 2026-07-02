/* Systematic, terms-driven note description — the "Esta Inversión (la Nota)…"
   blurb that fills itself out from the note's terms.

   Mirror of the Python source in `core/note_description.py` (used by the PDF
   report). Keep the two templates in sync if either changes. */
import type { NoteTerms } from '../api/types'
import type { Lang } from '../i18n/strings'

function duration(maturity: number, lang: Lang): string {
  const months = Math.round(maturity * 12)
  if (months % 12 === 0) {
    const y = months / 12
    if (lang === 'es') return y === 1 ? '1 año' : `${y} años`
    return y === 1 ? '1 year' : `${y} years`
  }
  return lang === 'es' ? `${months} meses` : `${months} months`
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
  const joined = joinNames(names, lang)
  const os = terms.one_star_level

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
    if (os != null) {
      const extra: string[] = []
      if (terms.one_star_coupon) extra.push('pagar el cupón')
      if (terms.one_star_autocall) extra.push('activar la cancelación anticipada')
      const lead = `Adicionalmente, bajo la característica One-Star, un único Subyacente en o por encima del ${p2(os)} de su nivel de Strike `
      s += extra.length
        ? lead + `basta por sí solo para ${extra.join(' y ')}, y para devolver el capital a la par en el vencimiento aunque el peor Subyacente haya perforado la Barrera de Knock-in. `
        : lead + `permite devolver el capital a la par en el vencimiento aunque el peor Subyacente haya perforado la Barrera de Knock-in (no afecta al cupón ni a la cancelación anticipada). `
    }
    s += `El Capital se encuentra en riesgo si la Nota no ha vencido anticipadamente y el Nivel Final de ${anyu} se ` +
      `encuentra por debajo del ${ki} de su nivel de Strike inicial en la Fecha de Observación Final.`
    return s
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
  if (os != null) {
    const extra: string[] = []
    if (terms.one_star_coupon) extra.push('pay the coupon')
    if (terms.one_star_autocall) extra.push('trigger early redemption')
    const lead = `In addition, under the One-Star feature, a single Underlying at or above ${p2(os)} of its Strike level `
    s += extra.length
      ? lead + `is enough on its own to ${extra.join(' and ')}, and to repay capital at par at maturity even if the worst Underlying has breached the Knock-in Barrier. `
      : lead + `repays capital at par at maturity even if the worst Underlying has breached the Knock-in Barrier (it does not affect the coupon or early-redemption conditions). `
  }
  s += `Capital is at risk if the Note has not redeemed early and the Final Level of ${anyu} is below ${ki} of its ` +
    `initial Strike level on the Final Observation Date.`
  return s
}
