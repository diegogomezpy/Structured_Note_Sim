import { useI18n } from '../i18n/I18nProvider'
import Panel from './Panel'
import Icon from './Icon'

/** Failed-run panel — Mercator · States. Rust icon tile, serif heading, the raw
    error in a mono box, and a Retry action. Replaces a bare red one-liner. */
export default function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useI18n()
  return (
    <Panel pad={40}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', maxWidth: 460, margin: '0 auto' }}>
        <div style={{
          width: 50, height: 50, borderRadius: 13, background: 'var(--red-weak)', color: 'var(--red)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16,
        }}><Icon name="x" size={26} /></div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 19, fontWeight: 600, letterSpacing: '-0.01em', marginBottom: 12 }}>
          {t('error_title')}
        </div>
        <div className="mono" style={{
          fontSize: 11.5, color: 'var(--red)', background: 'var(--red-weak)', border: '1px solid var(--red)',
          borderRadius: 6, padding: '8px 12px', marginBottom: 18, maxWidth: '100%', overflowWrap: 'anywhere',
        }}>{message}</div>
        <button className="btn btn--primary" onClick={onRetry}>
          <Icon name="refresh" size={14} /> {t('retry')}
        </button>
      </div>
    </Panel>
  )
}
