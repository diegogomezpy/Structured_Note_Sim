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
  // The generator emits the opening summary, then one paragraph per active
  // feature (step-down, One Star, Zenith, …). The first sentence is pulled out
  // as the lede; everything after it keeps its paragraph breaks.
  const [head, ...features] = text.split('\n\n')
  const idx = head.indexOf('. ')
  const lead = idx >= 0 ? head.slice(0, idx + 1) : head
  const rest = idx >= 0 ? head.slice(idx + 2) : ''
  const paras = [rest, ...features].filter(Boolean)

  return (
    <Section title={t('note_desc_section')}>
      <div className="fade-up" style={{ display: 'flex', gap: 16, paddingTop: 2 }}>
        <div style={{ width: 2, borderRadius: 2, background: 'var(--accent)', flexShrink: 0 }} />
        <div style={{ maxWidth: 680 }}>
          <p style={{ margin: paras.length ? '0 0 9px' : 0, fontFamily: 'var(--font-serif)', fontSize: 15.5, fontWeight: 600, lineHeight: 1.5, letterSpacing: '-0.01em', color: 'var(--text)' }}>
            {lead}
          </p>
          {paras.map((para, i) => (
            <p key={i} style={{ margin: i === paras.length - 1 ? 0 : '0 0 10px', fontSize: 13, lineHeight: 1.7, color: 'var(--text-muted)', textAlign: 'justify', hyphens: 'auto' }}>{para}</p>
          ))}
        </div>
      </div>
    </Section>
  )
}
