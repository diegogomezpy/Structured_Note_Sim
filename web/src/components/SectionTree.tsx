import Icon from './Icon'
import type { Group } from '../lib/reportSections'

/** Tri-state checkbox glyph shared by the report / batch section pickers. */
export function Check({ on, indeterminate }: { on: boolean; indeterminate?: boolean }) {
  return (
    <span style={{
      width: 17, height: 17, borderRadius: 5, flexShrink: 0,
      border: `1.5px solid ${on || indeterminate ? 'var(--accent)' : 'var(--border-strong)'}`,
      background: on || indeterminate ? 'var(--accent)' : 'transparent',
      display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff',
    }}>{on ? <Icon name="check" size={11} /> : indeterminate ? <span style={{ width: 7, height: 2, background: '#fff', borderRadius: 1 }} /> : null}</span>
  )
}

/** The grouped section catalogue as a checkbox tree. Group header toggles the
    whole group; each item toggles individually. Purely controlled — the parent
    owns `sel` and applies the toggles. */
export default function SectionTree({ groups, sel, onToggle, onToggleGroup, lang }: {
  groups: Group[]
  sel: Set<string>
  onToggle: (key: string) => void
  onToggleGroup: (g: Group) => void
  lang: string
}) {
  const lab = (en: string, es: string) => (lang === 'es' ? es : en)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '2px 24px' }}>
      {groups.map((g) => {
        const ks = g.items.map((i) => i[0])
        const onCount = ks.filter((k) => sel.has(k)).length
        return (
          <div key={g.key} style={{ marginBottom: 10 }}>
            <button onClick={() => onToggleGroup(g)}
              style={{ display: 'flex', alignItems: 'center', gap: 9, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '5px 0', width: '100%' }}>
              <Check on={onCount === ks.length} indeterminate={onCount > 0 && onCount < ks.length} />
              <span style={{ fontSize: 12.5, fontWeight: 700 }}>{lab(g.en, g.es)}</span>
            </button>
            {g.items.map(([k, en, es]) => (
              <button key={k} onClick={() => onToggle(k)}
                style={{ display: 'flex', alignItems: 'center', gap: 9, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: '4px 0 4px 24px', width: '100%' }}>
                <Check on={sel.has(k)} />
                <span style={{ fontSize: 12, color: 'var(--text)' }}>{lab(en, es)}</span>
              </button>
            ))}
          </div>
        )
      })}
    </div>
  )
}
