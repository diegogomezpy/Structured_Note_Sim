import type { ReactNode } from 'react'

export interface TabDef {
  id: string
  label: ReactNode
  disabled?: boolean
}

export default function Tabs({
  tabs, active, onChange,
}: { tabs: TabDef[]; active: string; onChange: (id: string) => void }) {
  return (
    <div style={{ display: 'flex', gap: 2, borderBottom: '1px solid var(--border)' }}>
      {tabs.map((tab) => {
        const on = tab.id === active
        return (
          <button key={tab.id} disabled={tab.disabled} onClick={() => onChange(tab.id)}
            style={{
              border: 'none', background: 'transparent', cursor: tab.disabled ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit', fontSize: 13.5, fontWeight: on ? 600 : 400, padding: '10px 16px',
              color: tab.disabled ? 'var(--text-faint)' : on ? 'var(--accent-text)' : 'var(--text-muted)',
              borderBottom: `2px solid ${on ? 'var(--accent)' : 'transparent'}`,
              marginBottom: -1, transition: 'color 0.12s ease',
            }}>
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}
