import { useI18n } from '../i18n/I18nProvider'
import { Section } from './fields'
import { noteDescription } from '../lib/noteDescription'
import type { NoteTerms } from '../api/types'

/** Systematic prose description of the note, generated from its terms — or the
    user's override when set. Mirrors core/note_description.py used by the PDF. */
export default function NoteDescription({ terms }: { terms: NoteTerms }) {
  const { t, lang } = useI18n()
  const text = (terms.note_description?.trim()) || noteDescription(terms, lang)
  return (
    <Section title={t('note_desc_section')} defaultOpen>
      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: 'var(--text-muted)' }}>{text}</p>
    </Section>
  )
}
