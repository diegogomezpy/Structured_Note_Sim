import { useRef, useState } from 'react'
import Icon from './Icon'

/* Bespoke form primitives shared by the PDF Designer and the Build tab's
   per-report image picker. Purpose-built (colour wells, upload tiles, cards)
   rather than reused generic controls. */

export function dataUrl(v?: string): string | undefined {
  if (!v) return undefined
  if (v.startsWith('data:') || v.startsWith('http') || v.startsWith('/')) return v
  let mime = 'image/png'
  if (v.startsWith('/9j/')) mime = 'image/jpeg'
  else if (v.startsWith('R0lGOD')) mime = 'image/gif'
  else if (v.startsWith('UklGR')) mime = 'image/webp'
  else if (v.startsWith('iVBOR')) mime = 'image/png'
  else if (v.includes('ftyp') || v.startsWith('AAAA')) mime = 'image/avif'
  return `data:${mime};base64,${v}`
}

export const inputStyle: React.CSSProperties = {
  width: '100%', fontSize: 13, padding: '9px 11px', borderRadius: 9,
  border: '1px solid var(--border)', background: 'var(--bg-elev, var(--surface-2))', color: 'var(--text)',
}

export const grid = (min = 180): React.CSSProperties => ({
  display: 'grid', gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))`, gap: 12,
})

const CARD_LS = 'mercator_designer_cards'

function readCardState(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem(CARD_LS) || '{}') } catch { return {} }
}
function writeCardState(id: string, open: boolean) {
  try {
    const s = readCardState(); s[id] = open
    localStorage.setItem(CARD_LS, JSON.stringify(s))
  } catch { /* ignore */ }
}

/** A collapsible settings island. Open by default (nothing hides unexpectedly),
    and each card remembers its own open/closed state across sessions so a long
    studio can be folded down to just the sections you're working in. */
export function Card({ id, title, desc, children, tight, defaultOpen = true }: {
  id?: string; title: string; desc?: string; children: React.ReactNode
  tight?: boolean; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(() => {
    if (!id) return defaultOpen
    const saved = readCardState()[id]
    return typeof saved === 'boolean' ? saved : defaultOpen
  })
  const toggle = () => {
    setOpen((o) => { const n = !o; if (id) writeCardState(id, n); return n })
  }
  const pad = tight ? '14px 16px' : '16px 18px'
  return (
    <section style={{ border: '1px solid var(--border)', borderRadius: 14, background: 'var(--surface)' }}>
      <button type="button" onClick={toggle} aria-expanded={open}
        style={{
          width: '100%', display: 'flex', alignItems: 'flex-start', gap: 10, textAlign: 'left',
          background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit',
          padding: open ? `${pad.split(' ')[0]} ${pad.split(' ')[1]} 0` : pad, color: 'var(--text)',
        }}>
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: 'block', fontSize: 13.5, fontWeight: 800, letterSpacing: '-0.01em' }}>{title}</span>
          {desc && <span style={{ display: 'block', fontSize: 11.5, color: 'var(--text-faint)', marginTop: 3, lineHeight: 1.5 }}>{desc}</span>}
        </span>
        <span aria-hidden style={{
          flexShrink: 0, color: 'var(--text-faint)', fontSize: 15, lineHeight: 1, marginTop: 2,
          transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 140ms ease',
        }}>›</span>
      </button>
      {open && <div style={{ padding: `13px ${pad.split(' ')[1]} ${pad.split(' ')[0]}` }}>{children}</div>}
    </section>
  )
}

/** A number input you can actually empty.

    A plain controlled `type="number"` bound to a number can never be blank: the
    moment you select-all and delete, the value round-trips back through the
    parent and the old digits reappear, so you have to edit around whatever is
    already there. This keeps the raw text locally while the field has focus, so
    it may be empty or half-typed ("0.", "-", ""), and only commits values that
    parse. Clamping waits for blur — clamping per keystroke turns typing "0.5"
    into "0" the instant the "0" lands. Leaving the field empty restores the
    previous value rather than writing a bogus one. */
export function NumberInput({ value, onChange, min, max, step, placeholder, style }: {
  value: number | undefined
  onChange: (v: number) => void
  min?: number; max?: number; step?: number
  placeholder?: string
  style?: React.CSSProperties
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const clamp = (n: number) =>
    Math.min(max ?? Number.POSITIVE_INFINITY, Math.max(min ?? Number.NEGATIVE_INFINITY, n))

  return (
    <input
      type="number" min={min} max={max} step={step} placeholder={placeholder}
      value={draft ?? (value == null || Number.isNaN(value) ? '' : String(value))}
      onChange={(e) => {
        const raw = e.target.value
        setDraft(raw)
        const n = Number(raw)
        if (raw !== '' && Number.isFinite(n)) onChange(n)   // unclamped while typing
      }}
      onBlur={() => {
        const n = Number(draft)
        if (draft !== null && draft !== '' && Number.isFinite(n)) onChange(clamp(n))
        setDraft(null)                                     // fall back to the committed value
      }}
      style={{ ...inputStyle, ...style }}
    />
  )
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'block' }}>
      <span style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 5, letterSpacing: '0.01em' }}>{label}</span>
      {children}
    </label>
  )
}

export function TextInput({ value, onChange, placeholder }: { value?: string; onChange: (v: string) => void; placeholder?: string }) {
  return <input type="text" value={value ?? ''} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} style={inputStyle} />
}

/** A colour "well": a rounded swatch that opens the native picker, plus a hex
    readout you can type into. */
export function ColorWell({ label, value, fallback, onChange }: { label: string; value?: string; fallback: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLInputElement>(null)
  const shown = value || fallback
  return (
    <div>
      <span style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 5 }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button type="button" onClick={() => ref.current?.click()} aria-label={label}
          style={{ width: 30, height: 30, borderRadius: 8, border: '1px solid var(--border-strong)', background: shown, cursor: 'pointer', flexShrink: 0, padding: 0 }} />
        <input ref={ref} type="color" value={shown} onChange={(e) => onChange(e.target.value)}
          style={{ position: 'absolute', width: 0, height: 0, opacity: 0, pointerEvents: 'none' }} />
        <input type="text" value={value ?? ''} placeholder={fallback} onChange={(e) => onChange(e.target.value)}
          style={{ ...inputStyle, fontFamily: 'var(--font-mono, monospace)', fontSize: 12, padding: '7px 9px' }} />
      </div>
    </div>
  )
}

/** An image slot: a thumbnail that opens the file picker, with upload/clear. */
export function UploadTile({ label, src, onPick, onClear, dark, accept = 'image/*' }: {
  label: string; src?: string; onPick: (f: File | undefined) => void; onClear: () => void; dark?: boolean; accept?: string
}) {
  const ref = useRef<HTMLInputElement>(null)
  const url = dataUrl(src)
  return (
    <div>
      <span style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 5 }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button type="button" onClick={() => ref.current?.click()}
          style={{ width: 58, height: 38, borderRadius: 9, border: '1px dashed var(--border-strong)', background: url ? (dark ? '#0e1310' : 'var(--surface-2)') : 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', padding: 3 }}>
          {url ? <img src={url} alt="" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} /> : <Icon name="upload" size={15} />}
        </button>
        <div style={{ display: 'flex', gap: 6 }}>
          <button type="button" className="btn btn--ghost" style={{ padding: '5px 9px', fontSize: 12 }} onClick={() => ref.current?.click()}>Upload</button>
          {src && <button type="button" className="btn btn--ghost" style={{ padding: '5px 9px', fontSize: 12 }} onClick={onClear}>Clear</button>}
        </div>
        <input ref={ref} type="file" accept={accept} style={{ display: 'none' }} onChange={(e) => { onPick(e.target.files?.[0]); e.target.value = '' }} />
      </div>
    </div>
  )
}
