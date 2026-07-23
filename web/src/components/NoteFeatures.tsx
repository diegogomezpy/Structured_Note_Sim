import { useI18n } from '../i18n/I18nProvider'
import { noteTermRows } from '../lib/terms'
import type { NoteTerms } from '../api/types'

/** The note's terms at a glance — the same fields the PDF's Note Terms table
    shows (see lib/terms.ts:noteTermRows). A compact key/value grid so the reader
    can scan the structure without parsing the prose below it. */
export default function NoteFeatures({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  const rows = noteTermRows(terms, t)

  return (
    <div>
      <div style={{
        fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
        color: 'var(--text-faint)', marginBottom: 8,
      }}>{t('nd_features')}</div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
        gap: '0 24px',
      }}>
        {rows.map(([label, value]) => (
          <div key={label} style={{
            display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
            gap: 12, padding: '6px 0', borderBottom: '1px solid var(--border)',
          }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{label}</span>
            <span className="mono" style={{ fontSize: 12, color: 'var(--text)', textAlign: 'right' }}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
