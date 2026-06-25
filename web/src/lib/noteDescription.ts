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

const p2 = (x: number) => `${(x * 100).toFixed(2)}%`

/** Generate the prose note description from `terms` (en/es). */
export function noteDescription(terms: NoteTerms, lang: Lang): string {
  const names = Object.values(terms.tickers ?? {})
  const multi = names.length > 1
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
    if (os != null)
      s += `Adicionalmente, bajo la característica One-Star, un único Subyacente en o por encima del ${p2(os)} de su ` +
        `nivel de Strike basta por sí solo para satisfacer las condiciones de cupón, cancelación anticipada y ` +
        `devolución de capital. `
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
  if (os != null)
    s += `In addition, under the One-Star feature, a single Underlying at or above ${p2(os)} of its Strike level on ` +
      `its own satisfies the coupon, early-redemption and capital-repayment conditions. `
  s += `Capital is at risk if the Note has not redeemed early and the Final Level of ${anyu} is below ${ki} of its ` +
    `initial Strike level on the Final Observation Date.`
  return s
}
