import type { ReactNode } from 'react'
import Icon from './Icon'
import { useI18n } from '../i18n/I18nProvider'

/** A titled surface card. `right` renders in the header row (e.g. a caption). */
export default function Panel({
  title, right, children, pad = 18, className,
}: {
  title?: ReactNode
  right?: ReactNode
  children: ReactNode
  pad?: number
  className?: string
}) {
  // When the body is flush (pad=0, e.g. an edge-to-edge table) the header still
  // needs its own inset — otherwise the title's accent bar spills past the card's
  // rounded border instead of sitting inside it.
  const flush = pad === 0
  return (
    <div className={`card ${className ?? ''}`} style={{ padding: pad }}>
      {(title || right) && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, gap: 12, ...(flush ? { padding: '18px 18px 0' } : null) }}>
          {title && <div className="panel-title">{title}</div>}
          {right && <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{right}</div>}
        </div>
      )}
      {children}
    </div>
  )
}

/** A Panel showing a centred spinner + "loading" caption — the shared loading
    state for path-explorer / backtest / underlying panels. */
export function LoadingPanel({ pad = 40, size = 18 }: { pad?: number; size?: number }) {
  const { t } = useI18n()
  return (
    <Panel pad={pad}>
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 14 }}>
        <Icon name="spinner" size={size} /> {t('loading')}
      </div>
    </Panel>
  )
}
