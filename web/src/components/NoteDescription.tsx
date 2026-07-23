import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { Section } from './fields'
import NoteFeatures from './NoteFeatures'
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

  const paras = text ? text.split('\n\n').filter(Boolean) : []

  return (
    <Section title={t('note_desc_section')}>
      {/* The features table first — a quick scan of the note's terms, the same
          fields as the PDF's Note Terms table — then the prose below it. The
          table comes from the terms directly, so it shows even before (or if)
          the server-generated description arrives. */}
      <NoteFeatures terms={terms} />
      {paras.length > 0 && (
        <div className="fade-up" style={{ display: 'flex', gap: 16, marginTop: 18 }}>
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
      )}
    </Section>
  )
}
