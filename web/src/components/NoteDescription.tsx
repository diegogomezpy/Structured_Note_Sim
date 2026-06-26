import { useI18n } from '../i18n/I18nProvider'
import { Section } from './fields'
import { noteDescription } from '../lib/noteDescription'
import type { NoteTerms } from '../api/types'

/** Systematic prose description of the note, generated from its terms — or the
    user's override when set. Presented editorially: the opening sentence leads in
    the serif voice beside a viridian rule, the remainder in a comfortable body
    measure. Mirrors core/note_description.py used by the PDF. */
export default function NoteDescription({ terms }: { terms: NoteTerms }) {
  const { t, lang } = useI18n()
  const text = (terms.note_description?.trim()) || noteDescription(terms, lang)
  const idx = text.indexOf('. ')
  const lead = idx >= 0 ? text.slice(0, idx + 1) : text
  const rest = idx >= 0 ? text.slice(idx + 2) : ''

  return (
    <Section title={t('note_desc_section')}>
      <div className="fade-up" style={{ display: 'flex', gap: 16, paddingTop: 2 }}>
        <div style={{ width: 2, borderRadius: 2, background: 'var(--accent)', flexShrink: 0 }} />
        <div style={{ maxWidth: 680 }}>
          <p style={{ margin: rest ? '0 0 9px' : 0, fontFamily: 'var(--font-serif)', fontSize: 15.5, fontWeight: 600, lineHeight: 1.5, letterSpacing: '-0.01em', color: 'var(--text)' }}>
            {lead}
          </p>
          {rest && (
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.7, color: 'var(--text-muted)' }}>{rest}</p>
          )}
        </div>
      </div>
    </Section>
  )
}
