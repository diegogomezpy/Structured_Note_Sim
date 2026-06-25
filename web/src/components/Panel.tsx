import type { ReactNode } from 'react'

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
          {title && <div className="section-label">{title}</div>}
          {right && <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{right}</div>}
        </div>
      )}
      {children}
    </div>
  )
}
