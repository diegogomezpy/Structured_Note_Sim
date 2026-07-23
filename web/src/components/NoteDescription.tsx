import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { Section } from './fields'
import type { NoteTerms } from '../api/types'

/** The systematic prose description of the note, or the author's override.

    The text comes from the server. It used to be generated here as well, by a
    hand-maintained TypeScript copy of core/note_description.py — and the two
    drifted: Python printed "10.00%" where TypeScript printed "10%", and Python
    said "1 year" where TypeScript said "12 months", so the app and the PDF the
    client received described the same note differently. There is now one
    generator and one answer.

    Six paragraphs, justified, each answering one economic question. */
export default function NoteDescription({ terms }: { terms: NoteTerms }) {
  const { t, lang } = useI18n()
  const override = terms.note_description?.trim()
  const [text, setText] = useState(override ?? '')

  // Re-fetch whenever anything the prose reads changes. Serialising the terms is
  // the honest dependency: it is exactly what the server is handed, so a field
  // that affects the description cannot be forgotten here.
  const dep = JSON.stringify(terms)
  useEffect(() => {
    if (override) { setText(override); return }
    let live = true
    api.describeNote(terms, lang)
      .then((r) => { if (live) setText(r.text) })
      .catch(() => { if (live) setText('') })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dep, lang, override])

  if (!text) return null
  const paras = text.split('\n\n').filter(Boolean)

  return (
    <Section title={t('note_desc_section')}>
      <div className="fade-up" style={{ display: 'flex', gap: 16, paddingTop: 2 }}>
        <div style={{ width: 2, borderRadius: 2, background: 'var(--accent)', flexShrink: 0 }} />
        <div style={{ maxWidth: 680 }}>
          {paras.map((para, i) => (
            <p key={i} style={{
              margin: i === paras.length - 1 ? 0 : '0 0 11px',
              fontSize: 13, lineHeight: 1.7, color: 'var(--text-muted)',
              textAlign: 'justify', hyphens: 'auto',
            }}>{para}</p>
          ))}
        </div>
      </div>
    </Section>
  )
}
