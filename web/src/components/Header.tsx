import { useTheme } from '../theme/ThemeProvider'
import { useI18n } from '../i18n/I18nProvider'
import Icon from './Icon'
import BrandMark from './BrandMark'
import TickerLogo, { IssuerLogo } from './TickerLogo'
import type { NoteTerms } from '../api/types'

export interface RunMeta { engine: string; nPaths: number; stale: boolean }

function compactPaths(n: number): string {
  return n >= 1000 ? `${Math.round(n / 1000)}k` : String(n)
}

export default function Header({ terms, run }: { terms: NoteTerms | null; run: RunMeta | null }) {
  const { mode, toggle } = useTheme()
  const { lang, setLang, t } = useI18n()
  const tickers = terms ? Object.entries(terms.tickers ?? {}) : []

  return (
    <header style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18,
      padding: '11px clamp(14px, 1.6vw, 28px)', background: 'var(--header-bg)',
      borderBottom: '1px solid var(--border)', boxShadow: 'var(--shadow)', position: 'relative', zIndex: 5,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, minWidth: 0 }}>
        {/* brand — Mercator wordmark + meridian mark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 11, flexShrink: 0 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 7, background: 'var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fffefb',
          }}>
            <BrandMark size={20} />
          </div>
          <span style={{ fontFamily: 'var(--font-serif)', fontSize: 19, fontWeight: 600, letterSpacing: '-0.01em' }}>Mercator</span>
        </div>

        {/* active instrument readout — serif title (Pricer doc) + mono subtitle */}
        {terms && (
          <>
            <span style={{ width: 1, height: 30, background: 'var(--border)', flexShrink: 0 }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
              {terms.issuer && <IssuerLogo issuer={terms.issuer} size={26} />}
              <div style={{ minWidth: 0 }}>
                {terms.name && (
                  <div style={{ fontFamily: 'var(--font-serif)', fontSize: 14.5, fontWeight: 600, lineHeight: 1.15, letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {terms.name}
                  </div>
                )}
                <div className="mono" style={{ fontSize: 10.5, color: 'var(--text-faint)', display: 'flex', alignItems: 'center', gap: 6, marginTop: terms.name ? 2 : 0 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {tickers.map(([sym, name]) => <TickerLogo key={sym} symbol={sym} name={name} size={15} />)}
                  </span>
                  {terms.maturity}y · {t('worst_of')}
                  {tickers.length > 0 && ` · ${tickers.map(([sym]) => sym).join('/')}`}
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        {run && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span className="mono" style={{ fontSize: 11, color: 'var(--text-faint)' }}>
              {run.engine} · {compactPaths(run.nPaths)}
            </span>
            <span className="pill" style={{
              background: run.stale ? 'var(--amber-weak)' : 'var(--green-weak)',
              color: run.stale ? 'var(--amber)' : 'var(--green)',
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
              {run.stale ? t('status_stale') : t('status_current')}
            </span>
          </div>
        )}
        <div style={{ display: 'flex', border: '1px solid var(--border-strong)', borderRadius: 999, overflow: 'hidden' }}>
          {(['en', 'es'] as const).map((l) => (
            <button key={l} onClick={() => setLang(l)}
                    style={{
                      border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, padding: '5px 12px',
                      fontFamily: 'inherit',
                      background: lang === l ? 'var(--accent)' : 'transparent',
                      color: lang === l ? '#fff' : 'var(--text-muted)',
                    }}>
              {l.toUpperCase()}
            </button>
          ))}
        </div>
        <button className="btn btn--ghost" onClick={toggle} aria-label="Toggle theme" style={{ padding: 8 }}>
          <Icon name={mode === 'light' ? 'moon' : 'sun'} size={17} />
        </button>
      </div>
    </header>
  )
}
