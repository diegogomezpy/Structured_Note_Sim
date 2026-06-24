import { useState, type ReactNode } from 'react'

const labelStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }

/** Label + right-aligned value readout above a control (used by sliders). */
export function Field({ label, value, children }: { label: string; value?: ReactNode; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
        {value != null && <span className="mono" style={{ fontSize: 12, color: 'var(--text)' }}>{value}</span>}
      </div>
      {children}
    </div>
  )
}

export function Slider({
  label, value, min, max, step, fmt, onChange, disabled,
}: {
  label: string; value: number; min: number; max: number; step: number
  fmt: (n: number) => string; onChange: (v: number) => void; disabled?: boolean
}) {
  return (
    <Field label={label} value={fmt(value)}>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
             onChange={(e) => onChange(parseFloat(e.target.value))} style={disabled ? { opacity: 0.4 } : undefined} />
    </Field>
  )
}

/** Numeric input. When `percent`, the stored value is a fraction but the field
    shows/accepts a percentage (e.g. 0.5 ↔ "50"). */
export function NumberField({
  label, value, onChange, min, max, step = 0.5, percent, suffix,
}: {
  label: string; value: number; onChange: (v: number) => void
  min?: number; max?: number; step?: number; percent?: boolean; suffix?: string
}) {
  const disp = percent ? Math.round(value * 1000) / 10 : value
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={labelStyle}>{label}{suffix ? ` (${suffix})` : ''}</label>
      <input type="number" value={disp} min={min} max={max} step={step}
             onChange={(e) => {
               const v = parseFloat(e.target.value)
               if (!Number.isNaN(v)) onChange(percent ? v / 100 : v)
             }} />
    </div>
  )
}

export function SelectField<T extends string>({
  label, value, options, onChange,
}: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={labelStyle}>{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

export function ToggleField({
  label, checked, onChange,
}: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 13, color: 'var(--text-muted)', cursor: 'pointer', marginBottom: 12 }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} style={{ width: 'auto' }} />
      {label}
    </label>
  )
}

export function TextField({
  label, value, onChange, placeholder,
}: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={labelStyle}>{label}</label>
      <input type="text" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

/** Collapsible accordion section for grouping advanced controls in the rail. */
export function Section({
  title, defaultOpen = false, children,
}: { title: string; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{ borderTop: '1px solid var(--border)' }}>
      <button onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit',
          padding: '13px 0 11px', color: 'var(--text)',
        }}>
        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{title}</span>
        <span style={{ transition: 'transform 0.15s ease', transform: open ? 'rotate(90deg)' : 'none', color: 'var(--text-faint)', fontSize: 13 }}>›</span>
      </button>
      {open && <div style={{ paddingBottom: 6 }}>{children}</div>}
    </div>
  )
}
