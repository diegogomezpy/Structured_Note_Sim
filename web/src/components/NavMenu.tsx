import Icon, { type Name as IconName } from './Icon'

/* Vertical navigation for the rail — every view and sub-view in one tree. The
   active view expands to reveal its sub-views (accordion), so the menu stays
   short while still exposing the whole app. On phones the rail is hidden, so the
   horizontal tab rows in the main column take over (see .nav-mobile-only). */

export interface NavSub { id: string; label: string }
export interface NavItem { id: string; label: string; icon?: IconName; subs?: NavSub[] }

export default function NavMenu({ items, tab, subs, onSelect }: {
  items: NavItem[]
  tab: string
  /** Remembered sub-view per view id, so switching away and back restores it. */
  subs: Record<string, string>
  onSelect: (tab: string, sub?: string) => void
}) {
  return (
    <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {items.map((it) => {
        const on = it.id === tab
        return (
          <div key={it.id}>
            <button onClick={() => onSelect(it.id)} aria-current={on ? 'page' : undefined}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 9, textAlign: 'left',
                fontFamily: 'inherit', fontSize: 13.5, fontWeight: on ? 600 : 500,
                padding: '9px 11px', borderRadius: 9, cursor: 'pointer', border: 'none',
                background: on ? 'var(--accent-weak)' : 'transparent',
                color: on ? 'var(--accent-text)' : 'var(--text-muted)',
                transition: 'background var(--dur-base) var(--ease-settle), color var(--dur-base) var(--ease-settle)',
              }}>
              {it.icon && <Icon name={it.icon} size={14} />}
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.label}</span>
              {it.subs && (
                <span aria-hidden style={{
                  fontSize: 12, opacity: 0.55, lineHeight: 1,
                  transform: on ? 'rotate(90deg)' : 'none',
                  transition: 'transform var(--dur-base) var(--ease-settle)',
                }}>›</span>
              )}
            </button>
            {on && it.subs && (
              <div style={{
                margin: '2px 0 6px 17px', paddingLeft: 11, borderLeft: '1px solid var(--border)',
                display: 'flex', flexDirection: 'column', gap: 1,
              }}>
                {it.subs.map((s) => {
                  const son = subs[it.id] === s.id
                  return (
                    <button key={s.id} onClick={() => onSelect(it.id, s.id)}
                      aria-current={son ? 'true' : undefined}
                      style={{
                        textAlign: 'left', fontFamily: 'inherit', fontSize: 12.5,
                        fontWeight: son ? 600 : 400, padding: '6px 9px', borderRadius: 7,
                        cursor: 'pointer', border: 'none',
                        background: son ? 'var(--surface-2)' : 'transparent',
                        color: son ? 'var(--text)' : 'var(--text-faint)',
                        transition: 'background var(--dur-base) var(--ease-settle), color var(--dur-base) var(--ease-settle)',
                      }}>{s.label}</button>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </nav>
  )
}
