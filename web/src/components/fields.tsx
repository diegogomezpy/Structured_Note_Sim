import { useState, type ReactNode } from 'react'

const labelStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }

/** Label + right-aligned value readout above a control (used by sliders). */
export function Field({ label, value, children, tip }: { label: string; value?: ReactNode; children: ReactNode; tip?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span title={tip} style={{ fontSize: 12, color: 'var(--text-muted)', cursor: tip ? 'help' : undefined }}>{label}</span>
        {value != null && <span className="mono" style={{ fontSize: 12, color: 'var(--text)' }}>{value}</span>}
      </div>
      {children}
    </div>
  )
}

export function Slider({
  label, value, min, max, step, fmt, onChange, disabled, tip, tone = 'accent',
}: {
  label: string; value: number; min: number; max: number; step: number
  fmt: (n: number) => string; onChange: (v: number) => void; disabled?: boolean; tip?: string
  tone?: 'accent' | 'danger'
}) {
  // Value-driven filled track: viridian (or rust, for downside barriers) up to
  // the thumb, hairline beyond — matches the Pricer/Mobile sliders.
  const frac = max > min ? Math.min(1, Math.max(0, (value - min) / (max - min))) : 0
  const fill = tone === 'danger' ? 'var(--red)' : 'var(--accent)'
  const valColor = tone === 'danger' ? 'var(--red)' : 'var(--text)'
  return (
    <Field label={label} value={<span style={{ color: valColor }}>{fmt(value)}</span>} tip={tip}>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
             className={tone === 'danger' ? 'range--danger' : undefined}
             onChange={(e) => onChange(parseFloat(e.target.value))}
             style={{
               opacity: disabled ? 0.4 : 1,
               background: `linear-gradient(90deg, ${fill} ${frac * 100}%, var(--border-strong) ${frac * 100}%)`,
             }} />
    </Field>
  )
}

/** Numeric input. When `percent`, the stored value is a fraction but the field
    shows/accepts a percentage (e.g. 0.5 ↔ "50"). */
export function NumberField({
  label, value, onChange, min, max, step = 0.5, percent, suffix, hint, error,
}: {
  label: string; value: number; onChange: (v: number) => void
  min?: number; max?: number; step?: number; percent?: boolean; suffix?: string; hint?: string
  error?: string
}) {
  const disp = percent ? Math.round(value * 1000) / 10 : value
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={labelStyle}>{label}{suffix ? ` (${suffix})` : ''}</label>
      <input type="number" value={disp} min={min} max={max} step={step}
             className={error ? 'field-invalid' : undefined}
             onChange={(e) => {
               const v = parseFloat(e.target.value)
               if (!Number.isNaN(v)) onChange(percent ? v / 100 : v)
             }} />
      {error
        ? <div className="field-msg">{error}</div>
        : hint && <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 5, lineHeight: 1.45 }}>{hint}</div>}
    </div>
  )
}

export function SelectField<T extends string>({
  label, value, options, onChange, tip,
}: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; tip?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ ...labelStyle, cursor: tip ? 'help' : undefined }} title={tip}>{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

/** Segmented control — mutually-exclusive choices as a pill (engine, frequency,
    range). Replaces a <select> when the options are few and worth showing inline. */
export function Segmented<T extends string>({
  value, options, onChange, ariaLabel,
}: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; ariaLabel?: string }) {
  return (
    <div className="seg" role="group" aria-label={ariaLabel} style={{ width: '100%' }}>
      {options.map((o) => (
        <button key={o.value} type="button" className={o.value === value ? 'seg--on' : undefined}
          aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Labelled segmented control (matches SelectField's label treatment). */
export function SegmentedField<T extends string>({
  label, value, options, onChange, tip,
}: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; tip?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ ...labelStyle, cursor: tip ? 'help' : undefined }} title={tip}>{label}</label>
      <Segmented value={value} options={options} onChange={onChange} ariaLabel={label} />
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
