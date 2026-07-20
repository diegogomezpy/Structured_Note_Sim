import { useI18n } from '../i18n/I18nProvider'
import { Section } from './fields'
import { nObs, couponRate, monthsNum } from '../lib/terms'
import { detectNoteType } from '../lib/noteType'
import { num, pct } from '../lib/format'
import type { NoteTerms } from '../api/types'

/** The note's observation calendar, derived from terms (no simulation needed):
    per period — time, coupon rate, and whether the autocall is eligible. A
    Participation note is a single maturity payoff (no coupon/autocall/observation
    ladder), so the schedule doesn't apply — it renders nothing there. */
export default function ObservationSchedule({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  if (detectNoteType(terms) === 'participation') return null
  const n = nObs(terms)
  const start = terms.autocall_start_period
  const cr = couponRate(terms)

  return (
    <Section title={t('obs_schedule')}>
      <div style={{ overflowX: 'auto' }}>
        <table className="ledger">
          <thead><tr>
            <th>{t('col_period')}</th>
            <th className="num">{t('col_time')}</th>
            <th className="num">{t('col_coupon_rate')}</th>
            <th className="num">{t('col_eligible')}</th>
          </tr></thead>
          <tbody>
            {Array.from({ length: n }, (_, i) => {
              const j = i + 1
              const eligible = j >= start
              return (
                <tr key={j}>
                  <td>P{j}</td>
                  <td className="num" style={{ color: 'var(--text-muted)' }}>{num(monthsNum((terms.maturity * j) / n), 1)}</td>
                  <td className="num">{pct(cr, 2)}</td>
                  <td className="num" style={{ color: eligible ? 'var(--text)' : 'var(--text-faint)' }}>
                    {eligible ? t('yes') : t('coupon_only')}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Section>
  )
}
