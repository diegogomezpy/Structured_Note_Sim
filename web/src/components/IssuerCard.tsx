import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import Icon from './Icon'
import { Section } from './fields'
import { IssuerLogo } from './TickerLogo'
import type { NoteTerms } from '../api/types'

/** A single agency rating chip (S&P / Moody's / Fitch). */
function Rating({ label, value }: { label: string; value: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'baseline', gap: 6, padding: '4px 10px', borderRadius: 8,
      background: 'var(--surface-2)', border: '1px solid var(--border)', fontSize: 11.5,
    }}>
      <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>{label}</span>
      <span className="mono" style={{ fontWeight: 700, color: 'var(--text)' }}>{value}</span>
    </span>
  )
}

/** Issuer card for the note-structure panel: logo + name + agency ratings, with
    a business description. The description prefers a curated `issuer_description`
    on the terms; otherwise it auto-loads (and translates) the issuer's profile
    from Yahoo — so it is preloaded the moment a note opens and re-translates when
    the language changes. Hidden when no issuer is set. */
export default function IssuerCard({ terms }: { terms: NoteTerms }) {
  const { t, lang } = useI18n()
  const [expanded, setExpanded] = useState(false)
  const [fetched, setFetched] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const issuer = terms.issuer || ''
  const curated = terms.issuer_description || ''
  // Cache the in-flight key so we don't refetch on unrelated term edits.
  const lastKey = useRef('')

  // Prefetch runs regardless of the section's collapsed state (the effect lives
  // in this always-mounted component, not inside the collapsible body) so the
  // profile is ready the instant the section is opened.
  useEffect(() => {
    setExpanded(false)
    if (!issuer || curated) { setFetched(null); return }
    const key = `${issuer}|${lang}`
    if (key === lastKey.current) return
    lastKey.current = key
    let cancelled = false
    setLoading(true)
    api.describe(issuer, [], lang)
      .then((r) => { if (!cancelled) setFetched(r.issuer_description || null) })
      .catch(() => { if (!cancelled) setFetched(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [issuer, curated, lang])

  if (!issuer) return null

  const ratings: [string, string][] = [
    [t('rating_sp'), terms.issuer_rating_sp],
    [t('rating_moody'), terms.issuer_rating_moody],
    [t('rating_fitch'), terms.issuer_rating_fitch],
  ].filter(([, v]) => v) as [string, string][]

  const desc = curated || fetched || ''
  // Editorial split: lead sentence in the serif voice, the rest as body (mirrors
  // the note description). The remainder clamps to a few lines until expanded.
  const idx = desc.indexOf('. ')
  const lead = idx >= 0 ? desc.slice(0, idx + 1) : desc
  const rest = idx >= 0 ? desc.slice(idx + 2) : ''
  const long = rest.length > 200

  return (
    <Section title={t('issuer_section')}>
      <div className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <IssuerLogo issuer={issuer} size={34} />
          <span style={{ fontSize: 15, fontWeight: 600 }}>{issuer}</span>
          {ratings.length > 0 && (
            <div style={{ display: 'flex', gap: 7, marginLeft: 'auto', flexWrap: 'wrap' }}>
              {ratings.map(([l, v]) => <Rating key={l} label={l} value={v} />)}
            </div>
          )}
        </div>

        {loading && !desc ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, color: 'var(--text-muted)', fontSize: 12.5 }}>
            <Icon name="spinner" size={14} /> {t('issuer_loading')}
          </div>
        ) : desc ? (
          <div className="fade-up" style={{ display: 'flex', gap: 14 }}>
            <div style={{ width: 2, borderRadius: 2, background: 'var(--accent)', flexShrink: 0 }} />
            <div style={{ maxWidth: 660 }}>
              <p style={{ margin: rest ? '0 0 8px' : 0, fontFamily: 'var(--font-serif)', fontSize: 14.5, fontWeight: 600, lineHeight: 1.5, letterSpacing: '-0.01em', color: 'var(--text)' }}>{lead}</p>
              {rest && (
                <>
                  <p style={expanded || !long ? { margin: 0, fontSize: 12.5, lineHeight: 1.65, color: 'var(--text-muted)' } : { margin: 0, fontSize: 12.5, lineHeight: 1.65, color: 'var(--text-muted)', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{rest}</p>
                  {long && (
                    <button onClick={() => setExpanded((o) => !o)} style={{ display: 'block', marginTop: 5, background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--accent-text)', fontSize: 11.5, fontFamily: 'inherit' }}>
                      {expanded ? t('ul_less') : t('ul_more')}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>{t('issuer_no_desc')}</div>
        )}
      </div>
    </Section>
  )
}
