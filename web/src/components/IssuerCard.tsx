import { useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import { Section } from './fields'
import { IssuerLogo } from './TickerLogo'
import type { NoteTerms } from '../api/types'

function Rating({ label, value }: { label: string; value: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 5, padding: '3px 9px', borderRadius: 7, background: 'var(--surface-2)', fontSize: 12 }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span className="mono" style={{ fontWeight: 600 }}>{value}</span>
    </span>
  )
}

/** Issuer row for the note-structure panel: logo + name, agency ratings, and the
    issuer description. All sourced from terms — no fetch. Hidden when no issuer. */
export default function IssuerCard({ terms }: { terms: NoteTerms }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  if (!terms.issuer) return null

  const ratings: [string, string][] = [
    [t('rating_sp'), terms.issuer_rating_sp],
    [t('rating_moody'), terms.issuer_rating_moody],
    [t('rating_fitch'), terms.issuer_rating_fitch],
  ].filter(([, v]) => v) as [string, string][]
  const desc = terms.issuer_description || ''
  const long = desc.length > 220

  return (
    <Section title={t('issuer_section')}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: desc ? 12 : 0 }}>
        <IssuerLogo issuer={terms.issuer} size={30} />
        <span style={{ fontSize: 14, fontWeight: 600 }}>{terms.issuer}</span>
        <div style={{ display: 'flex', gap: 7, marginLeft: 'auto', flexWrap: 'wrap' }}>
          {ratings.map(([l, v]) => <Rating key={l} label={l} value={v} />)}
        </div>
      </div>
      {desc ? (
        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', lineHeight: 1.55 }}>
          <span style={open || !long ? undefined : { display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{desc}</span>
          {long && (
            <button onClick={() => setOpen((o) => !o)} style={{ display: 'block', marginTop: 4, background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--accent-text)', fontSize: 11.5, fontFamily: 'inherit' }}>
              {open ? t('ul_less') : t('ul_more')}
            </button>
          )}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>{t('issuer_no_desc')}</div>
      )}
    </Section>
  )
}
