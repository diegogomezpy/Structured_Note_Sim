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
  return (
    <div className={`card ${className ?? ''}`} style={{ padding: pad }}>
      {(title || right) && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, gap: 12 }}>
          {title && <div className="section-label">{title}</div>}
          {right && <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{right}</div>}
        </div>
      )}
      {children}
    </div>
  )
}
