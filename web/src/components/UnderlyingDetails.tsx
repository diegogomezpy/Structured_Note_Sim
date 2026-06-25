import { useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import Icon from './Icon'
import TickerLogo, { LogoImg } from './TickerLogo'
import { noteDescription } from '../lib/noteDescription'
import type { AnalystSplit, NoteTerms, Sentiment, UnderlyingOverride } from '../api/types'

const SENTIMENTS: Sentiment[] = ['buy', 'hold', 'sell']
export const SENTIMENT_COLOR: Record<Sentiment, string> = { buy: '#16a34a', hold: '#f59e0b', sell: '#dc2626' }

/** Editor for the per-underlying overrides (description, custom logo, analyst
    rating) and the issuer description — with a Prefill-from-Yahoo button that
    fills the descriptions from business summaries. Stored on terms.underlyings
    (keyed by display name) + terms.issuer_description. */
export default function UnderlyingDetails({ terms, onChange }: {
  terms: NoteTerms; onChange: (t: NoteTerms) => void
}) {
  const { t, lang } = useI18n()
  const [busy, setBusy] = useState(false)
  const fileRefs = useRef<Record<string, HTMLInputElement | null>>({})

  const ov = (name: string): UnderlyingOverride => terms.underlyings?.[name] ?? {}
  const setOverride = (name: string, patch: Partial<UnderlyingOverride>) => {
    const u = { ...(terms.underlyings ?? {}) }
    u[name] = { ...(u[name] ?? {}), ...patch }
    onChange({ ...terms, underlyings: u })
  }

  const prefill = async () => {
    setBusy(true)
    try {
      const syms = Object.keys(terms.tickers ?? {})
      const r = await api.describe(terms.issuer || null, syms, lang)
      const u = { ...(terms.underlyings ?? {}) }
      for (const [sym, name] of Object.entries(terms.tickers ?? {})) {
        const d = r.underlyings?.[sym]
        if (d) u[name] = { ...(u[name] ?? {}), description: d }
      }
      onChange({ ...terms, underlyings: u, issuer_description: r.issuer_description || terms.issuer_description })
    } catch { /* leave as-is */ } finally { setBusy(false) }
  }

  const onLogo = (name: string, file: File | undefined) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => setOverride(name, { logo: String(reader.result) })
    reader.readAsDataURL(file)
  }

  const ta: React.CSSProperties = {
    width: '100%', minHeight: 64, resize: 'vertical', fontFamily: 'inherit', fontSize: 12.5,
    lineHeight: 1.5, padding: '9px 11px', borderRadius: 9, border: '1px solid var(--border)',
    background: 'var(--surface)', color: 'var(--text)',
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn" style={{ padding: '7px 13px' }} onClick={prefill} disabled={busy}>
          <Icon name={busy ? 'spinner' : 'refresh'} size={14} /> {busy ? t('det_prefilling') : t('det_prefill')}
        </button>
      </div>

      {/* Note description (systematic; blank = auto-generate from the terms) */}
      <div style={{ marginBottom: 18 }}>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <span>{t('note_desc_label')}</span>
          <button className="btn btn--ghost" style={{ padding: '2px 9px', fontSize: 11 }}
                  onClick={() => onChange({ ...terms, note_description: noteDescription(terms, lang) })}>
            {t('note_desc_use_generated')}
          </button>
        </label>
        <textarea style={{ ...ta, minHeight: 96 }} value={terms.note_description ?? ''} placeholder={noteDescription(terms, lang)}
                  onChange={(e) => onChange({ ...terms, note_description: e.target.value })} />
        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 5 }}>{t('note_desc_hint')}</div>
      </div>

      {/* Issuer description */}
      <div style={{ marginBottom: 18 }}>
        <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('det_issuer_desc')}</label>
        <textarea style={ta} value={terms.issuer_description ?? ''}
                  onChange={(e) => onChange({ ...terms, issuer_description: e.target.value })} />
      </div>

      {/* Per-underlying */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {Object.entries(terms.tickers ?? {}).map(([sym, name]) => {
          const o = ov(name)
          return (
            <div key={sym} className="card" style={{ padding: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                {o.logo ? <LogoImg url={o.logo} name={name} size={24} /> : <TickerLogo symbol={sym} name={name} size={24} />}
                <span style={{ fontSize: 13.5, fontWeight: 600 }}>{name}</span>
                <span style={{ fontSize: 11.5, color: 'var(--text-faint)' }}>{sym}</span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                  <button className="btn btn--ghost" style={{ padding: '3px 8px', fontSize: 11.5 }} onClick={() => fileRefs.current[sym]?.click()}>
                    <Icon name="upload" size={12} /> {t('det_upload_logo')}
                  </button>
                  {o.logo && (
                    <button className="btn btn--ghost" style={{ padding: '3px 8px', fontSize: 11.5 }} onClick={() => setOverride(name, { logo: undefined })}>{t('det_reset_logo')}</button>
                  )}
                  <input ref={(el) => { fileRefs.current[sym] = el }} type="file" accept="image/*" style={{ display: 'none' }}
                         onChange={(e) => onLogo(name, e.target.files?.[0])} />
                </div>
              </div>

              <label style={{ fontSize: 11.5, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>{t('det_desc')}</label>
              <textarea style={ta} value={o.description ?? ''}
                        onChange={(e) => setOverride(name, { description: e.target.value })} />

              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 6 }}>{t('det_sentiment')}</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                  {SENTIMENTS.map((sv) => {
                    const a = o.analyst ?? { buy: 0, hold: 0, sell: 0 }
                    return (
                      <div key={sv}>
                        <label style={{ fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: SENTIMENT_COLOR[sv], display: 'block', marginBottom: 4 }}>{t(`sent_${sv}`)} %</label>
                        <input type="number" min={0} max={100} step={1} value={a[sv] || ''}
                               onChange={(e) => {
                                 const v = Math.max(0, Math.min(100, Number(e.target.value) || 0))
                                 const next: AnalystSplit = { ...a, [sv]: v }
                                 const empty = !next.buy && !next.hold && !next.sell
                                 setOverride(name, { analyst: empty ? null : next })
                               }} />
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
