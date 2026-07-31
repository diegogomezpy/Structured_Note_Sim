import { useMemo, useState } from 'react'
import Icon from './Icon'
import type { Group } from '../lib/reportSections'
import { useI18n } from '../i18n/I18nProvider'

/** Tri-state checkbox glyph shared by the report / batch section pickers. */
export function Check({ on, indeterminate, size = 17 }: { on: boolean; indeterminate?: boolean; size?: number }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: 5, flexShrink: 0,
      border: `1.5px solid ${on || indeterminate ? 'var(--accent)' : 'var(--border-strong)'}`,
      background: on || indeterminate ? 'var(--accent)' : 'transparent',
      display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff',
      transition: 'background var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease)',
    }}>{on ? <Icon name="check" size={Math.round(size * 0.65)} />
        : indeterminate ? <span style={{ width: Math.round(size * 0.42), height: 2, background: '#fff', borderRadius: 1 }} /> : null}</span>
  )
}

/** A rotating disclosure caret. No `chevron` in the Icon set, and one glyph here
    is cheaper than a shared icon nobody else needs. */
function Caret({ open }: { open: boolean }) {
  return (
    <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden
         style={{ flexShrink: 0, color: 'var(--text-faint)',
                  transform: `rotate(${open ? 90 : 0}deg)`,
                  transition: 'transform var(--dur-fast) var(--ease)' }}>
      <path d="M4 2.5 L8 6 L4 9.5" fill="none" stroke="currentColor" strokeWidth="1.6"
            strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** The grouped section catalogue as a checkbox tree.

    Laid out as COLLAPSIBLE CARDS flowing through balanced CSS columns rather than
    a fixed grid. The grid gave every group an equal-width column, so the tallest
    (Monte Carlo, 12 items) set the row height, the fifth group wrapped underneath
    the first, and three quarters of a screen-height row was empty — while the long
    A/B labels wrapped into a narrow ribbon. Columns let each card take the height
    it needs and fill the gap that follows it.

    Groups with nothing selected start collapsed: an unused lens should cost one
    line, not a column. `compact` is the batch panel's per-row density.

    Purely controlled — the parent owns `sel` and applies the toggles. */
export default function SectionTree({ groups, sel, onToggle, onToggleGroup, lang, compact, tourId }: {
  groups: Group[]
  sel: Set<string>
  onToggle: (key: string) => void
  onToggleGroup: (g: Group) => void
  lang: string
  compact?: boolean
  tourId?: string
}) {
  const { t } = useI18n()
  const lab = (en: string, es: string) => (lang === 'es' ? es : en)
  // Collapse whatever is entirely off at mount. Deliberately NOT re-derived from
  // `sel`: a group must not fold up underneath the pointer the moment its last
  // item is unticked.
  const [closed, setClosed] = useState<Set<string>>(
    () => new Set(groups.filter((g) => !g.items.some((i) => sel.has(i[0]))).map((g) => g.key)))
  const total = useMemo(() => groups.reduce((n, g) => n + g.items.length, 0), [groups])
  const chosen = useMemo(
    () => groups.reduce((n, g) => n + g.items.filter((i) => sel.has(i[0])).length, 0), [groups, sel])

  const setAll = (on: boolean) => {
    // `onToggleGroup` flips a group as a whole, so "all"/"none" is just the groups
    // that are not already in the target state. One code path, one source of truth.
    groups.forEach((g) => {
      const ks = g.items.map((i) => i[0])
      const allOn = ks.every((k) => sel.has(k))
      const anyOn = ks.some((k) => sel.has(k))
      if (on ? !allOn : anyOn) onToggleGroup(g)
    })
    if (on) setClosed(new Set())
  }

  // Deal the cards into columns, always adding to the shortest so far. Height is
  // estimated (header + rows when open, header alone when collapsed) rather than
  // measured — good enough to keep the columns level, and it needs no layout pass.
  const nCols = Math.min(groups.length, compact ? 2 : 3)
  const columns = useMemo(() => {
    const cols: Group[][] = Array.from({ length: Math.max(1, nCols) }, () => [])
    const h = new Array(Math.max(1, nCols)).fill(0)
    groups.forEach((g) => {
      const cost = 2 + (closed.has(g.key) ? 0 : g.items.length)
      const i = h.indexOf(Math.min(...h))
      cols[i].push(g); h[i] += cost
    })
    return cols
  }, [groups, nCols, closed])

  const pad = compact ? 8 : 11
  return (
    <div data-tour={tourId}>
      {/* Where the selection stands, and the two bulk actions. Reading "23 of 31"
          is the thing the old wall of checkboxes could not tell you at a glance. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                    marginBottom: compact ? 8 : 12 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
          {t('rep_sec_count', { n: String(chosen), total: String(total) })}
        </span>
        <span style={{ flex: 1 }} />
        <button type="button" className="btn btn--ghost" disabled={chosen === total}
                style={{ padding: '4px 10px', fontSize: 11.5 }} onClick={() => setAll(true)}>
          {t('rep_sec_all')}
        </button>
        <button type="button" className="btn btn--ghost" disabled={chosen === 0}
                style={{ padding: '4px 10px', fontSize: 11.5 }} onClick={() => setAll(false)}>
          {t('rep_sec_none')}
        </button>
      </div>

      {/* Deterministic masonry: cards are dealt to the shortest column so far,
          height estimated from the item count. CSS multi-column balancing was the
          obvious tool and it is not reliable here — with three cards it kept
          stacking two in the first column and leaving the third empty, which is
          the exact ragged void this replaced. Flex columns cannot do that. */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
        {columns.map((col, ci) => (
        <div key={ci} style={{ flex: 1, minWidth: 0 }}>
        {col.map((g) => {
          const ks = g.items.map((i) => i[0])
          const onCount = ks.filter((k) => sel.has(k)).length
          const open = !closed.has(g.key)
          const anyOn = onCount > 0
          return (
            <div key={g.key} style={{
              breakInside: 'avoid',
              display: 'inline-block', width: '100%', marginBottom: 12,
              border: `1px solid ${anyOn ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 10, overflow: 'hidden',
              background: anyOn ? 'var(--accent-weak)' : 'transparent',
              transition: 'border-color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: `${pad - 2}px ${pad}px` }}>
                {/* Two separate targets in one row: the box toggles the GROUP, the
                    title toggles OPEN. Making the whole header do both at once is
                    the ambiguity that made this feel unpredictable. */}
                <button type="button" onClick={() => onToggleGroup(g)}
                        title={onCount === ks.length ? t('rep_sec_none') : t('rep_sec_all')}
                        style={{ display: 'flex', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  <Check on={onCount === ks.length} indeterminate={onCount > 0 && onCount < ks.length} />
                </button>
                <button type="button" onClick={() => setClosed((p) => {
                          const n = new Set(p); n.has(g.key) ? n.delete(g.key) : n.add(g.key); return n
                        })}
                        aria-expanded={open}
                        style={{ display: 'flex', alignItems: 'center', gap: 7, flex: 1, minWidth: 0,
                                 background: 'none', border: 'none', cursor: 'pointer',
                                 fontFamily: 'inherit', padding: 0, textAlign: 'left' }}>
                  <span style={{ fontSize: compact ? 12 : 13, fontWeight: 700, flex: 1, minWidth: 0 }}>
                    {lab(g.en, g.es)}
                  </span>
                  <span style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--text-faint)',
                                 fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
                    {onCount}/{ks.length}
                  </span>
                  <Caret open={open} />
                </button>
              </div>
              {open && (
                <div style={{ padding: `0 ${pad}px ${pad - 3}px` }}>
                  {/* Only sections this note can actually produce reach here —
                      `groupsFor(sectionCtx(terms))` drops the rest, so there is no
                      such thing as a toggle that renders nothing. */}
                  {g.items.map(([k, en, es]) => (
                    <button key={k} type="button" onClick={() => onToggle(k)} className="sec-item"
                      style={{ display: 'flex', alignItems: 'flex-start', gap: 8,
                               background: 'none', border: 'none', cursor: 'pointer',
                               fontFamily: 'inherit', padding: '5px 6px', width: '100%',
                               borderRadius: 6, textAlign: 'left' }}>
                      <span style={{ marginTop: 1 }}><Check on={sel.has(k)} size={15} /></span>
                      <span style={{ flex: 1, minWidth: 0, fontSize: compact ? 11.5 : 12.5,
                                     color: 'var(--text)', lineHeight: 1.35 }}>
                        {lab(en, es)}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })}
        </div>
        ))}
      </div>
    </div>
  )
}
