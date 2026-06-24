import { useI18n } from '../i18n/I18nProvider'
import { Section } from './fields'
import { nObs, couponRate } from '../lib/terms'
import { num, pct } from '../lib/format'
import type { NoteTerms } from '../api/types'

const th: React.CSSProperties = {
  padding: '7px 12px', fontSize: 10.5, fontWeight: 600, letterSpacing: '0.05em',
  textTransform: 'uppercase', color: 'var(--text-muted)', borderBottom: '1px solid var(--border)',
}
const td: React.CSSProperties = { padding: '7px 12px', borderBottom: '1px solid var(--border)' }

/** The note's observation calendar, derived from terms (no simulation needed):
    per period — time, coupon rate, and whether the autocall is eligible. */
export default function ObservationSchedule({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  const n = nObs(terms)
  const start = terms.autocall_start_period
  const cr = couponRate(terms)

  return (
    <Section title={t('obs_schedule')}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead><tr>
            <th style={{ ...th, textAlign: 'left' }}>{t('col_period')}</th>
            <th style={{ ...th, textAlign: 'right' }}>{t('col_time')}</th>
            <th style={{ ...th, textAlign: 'right' }}>{t('col_coupon_rate')}</th>
            <th style={{ ...th, textAlign: 'right' }}>{t('col_eligible')}</th>
          </tr></thead>
          <tbody>
            {Array.from({ length: n }, (_, i) => {
              const j = i + 1
              const eligible = j >= start
              return (
                <tr key={j}>
                  <td className="mono" style={{ ...td, textAlign: 'left' }}>P{j}</td>
                  <td className="mono" style={{ ...td, textAlign: 'right', color: 'var(--text-muted)' }}>{num((terms.maturity * j) / n, 2)}</td>
                  <td className="mono" style={{ ...td, textAlign: 'right' }}>{pct(cr, 2)}</td>
                  <td style={{ ...td, textAlign: 'right', color: eligible ? 'var(--text)' : 'var(--text-faint)' }}>
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
