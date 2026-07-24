import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { InfoDot } from './Tooltip'

const labelStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }

/** A field label with an optional info dot carrying the tooltip. */
function FieldLabel({ label, tip, style }: { label: string; tip?: string; style?: React.CSSProperties }) {
  return (
    <span style={{ fontSize: 12, color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', ...style }}>
      {label}{tip && <InfoDot title={label} body={tip} />}
    </span>
  )
}

/** Label + right-aligned value readout above a control (used by sliders). */
export function Field({ label, value, children, tip }: { label: string; value?: ReactNode; children: ReactNode; tip?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <FieldLabel label={label} tip={tip} />
        {value != null && <span className="mono" style={{ fontSize: 12, color: 'var(--text)' }}>{value}</span>}
      </div>
      {children}
    </div>
  )
}

/** The numeric readout for a Slider, rendered as an inline editable input so the
    user can type an exact figure — including one beyond the slider's range (the
    slider thumb just pegs at its end). `pct` shows/accepts a percentage while the
    stored value stays a fraction (0.15 ↔ "15"). The buffer is only re-synced from
    the outside when the field isn't focused, so mid-edit typing is never clobbered. */
function EditableValue({
  value, pct, digits, prefix, suffix, isInt, clampMin = 0, clampMax, color, label, onCommit,
}: {
  value: number; pct?: boolean; digits: number
  prefix?: string; suffix?: string; isInt?: boolean
  clampMin?: number; clampMax?: number; color: string; label: string
  onCommit: (v: number) => void
}) {
  const toDisp = (v: number) => (pct ? v * 100 : v)
  const fromDisp = (d: number) => (pct ? d / 100 : d)
  // Up to `digits` decimals with trailing zeros trimmed, so a typed value keeps its
  // precision ("13.375") without padding round numbers ("10", not "10.000").
  const fmtDisp = (v: number) => (isInt ? String(Math.round(toDisp(v))) : String(parseFloat(toDisp(v).toFixed(digits))))
  const [focused, setFocused] = useState(false)
  const [text, setText] = useState(() => fmtDisp(value))
  useEffect(() => { if (!focused) setText(fmtDisp(value)) }, [value, focused])  // eslint-disable-line react-hooks/exhaustive-deps

  const commit = (raw: string) => {
    let n = parseFloat(raw)
    if (Number.isNaN(n)) return
    if (isInt) n = Math.round(n)
    if (clampMin != null) n = Math.max(clampMin, n)
    if (clampMax != null) n = Math.min(clampMax, n)
    onCommit(fromDisp(n))
  }

  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 1 }}>
      {prefix && <span className="mono" style={{ fontSize: 12, color }}>{prefix}</span>}
      <input
        type="text" inputMode="decimal" aria-label={label} className="slider-val-input mono"
        value={text}
        onChange={(e) => { setText(e.target.value); commit(e.target.value) }}
        onFocus={(e) => { setFocused(true); e.currentTarget.select() }}
        onBlur={() => { setFocused(false); setText(fmtDisp(value)) }}
        style={{ color, width: `${Math.max(2, text.length)}ch` }} />
      {suffix && <span className="mono" style={{ fontSize: 12, color }}>{suffix}</span>}
    </span>
  )
}

export function Slider({
  label, value, min, max, step, fmt, onChange, disabled, tip, tone = 'accent',
  editable = true, pct, editDigits = 3, editSuffix, editPrefix, editInt, editClamp,
}: {
  label: string; value: number; min: number; max: number; step: number
  fmt: (n: number) => string; onChange: (v: number) => void; disabled?: boolean; tip?: string
  tone?: 'accent' | 'danger'
  /** A typed readout (default). `pct` edits in percent; `editClamp` is [min, max?]
      in display units (max omitted ⇒ direct entry may exceed the slider's range). */
  editable?: boolean; pct?: boolean; editDigits?: number
  editSuffix?: string; editPrefix?: string; editInt?: boolean
  editClamp?: [number, number?]
}) {
  // Value-driven filled track: viridian (or rust, for downside barriers) up to
  // the thumb, hairline beyond — matches the Pricer/Mobile sliders.
  const frac = max > min ? Math.min(1, Math.max(0, (value - min) / (max - min))) : 0
  const fill = tone === 'danger' ? 'var(--red)' : 'var(--accent)'
  const valColor = tone === 'danger' ? 'var(--red)' : 'var(--text)'
  const readout = editable && !disabled
    ? <EditableValue value={value} pct={pct} digits={editDigits} prefix={editPrefix} suffix={editSuffix}
                     isInt={editInt} clampMin={editClamp?.[0]} clampMax={editClamp?.[1]}
                     color={valColor} label={label} onCommit={onChange} />
    : <span style={{ color: valColor }}>{fmt(value)}</span>
  return (
    <Field label={label} value={readout} tip={tip}>
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
    shows/accepts a percentage (e.g. 0.5 ↔ "50").

    Uses a rolling text buffer (like NumField/EditableValue) rather than a raw
    controlled `type="number"`: that lets the user clear the field and retype from
    empty (or edit the first digit) instead of the old value snapping back the
    instant the box is empty. An empty/partial buffer just isn't committed; the
    field re-syncs from the outside only while unfocused, so mid-edit typing is
    never clobbered, and it reformats on blur. `type="text" inputMode="decimal"`
    so intermediate strings like "12." survive (a number input reports those as
    "", losing the digits). */
export function NumberField({
  label, value, onChange, min, max, percent, suffix, hint, error, tip,
}: {
  label: string; value: number; onChange: (v: number) => void
  min?: number; max?: number; step?: number; percent?: boolean; suffix?: string; hint?: string
  error?: string; tip?: string
}) {
  const toDisp = (v: number) => (percent ? Math.round((v ?? 0) * 1000) / 10 : (v ?? 0))
  const fromDisp = (d: number) => (percent ? d / 100 : d)
  const fmtDisp = (v: number) => String(toDisp(v))
  const [focused, setFocused] = useState(false)
  const [text, setText] = useState(() => fmtDisp(value))
  useEffect(() => { if (!focused) setText(fmtDisp(value)) }, [value, focused])  // eslint-disable-line react-hooks/exhaustive-deps

  const commit = (raw: string) => {
    if (raw.trim() === '') return                 // allow an empty field mid-edit
    let n = parseFloat(raw)
    if (Number.isNaN(n)) return
    if (min != null) n = Math.max(min, n)
    if (max != null) n = Math.min(max, n)
    onChange(fromDisp(n))
  }

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ marginBottom: 6 }}><FieldLabel label={suffix ? `${label} (${suffix})` : label} tip={tip} /></div>
      <input
        type="text" inputMode="decimal" aria-label={label}
        value={text}
        className={error ? 'field-invalid' : undefined}
        onChange={(e) => { setText(e.target.value); commit(e.target.value) }}
        onFocus={(e) => { setFocused(true); e.currentTarget.select() }}
        onBlur={() => { setFocused(false); setText(fmtDisp(value)) }} />
      {error
        ? <div className="field-msg">{error}</div>
        : hint && <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 5, lineHeight: 1.45 }}>{hint}</div>}
    </div>
  )
}

/** Full-width numeric field the user types into — no slider track (those proved
    fiddly for the note terms). Free typing (text input, not a spinner) with a
    rolling text buffer so mid-edit values aren't clobbered; commits on change,
    clamped and rounded to `digits` decimals. `pct` stores a fraction but
    shows/accepts a percentage (0.1235 ↔ "12.35"). `min`/`max` are in *display*
    units. Mirrors EditableValue's parsing, presented as a labelled row. */
export function NumField({
  label, value, onChange, tip, pct, digits = 3, suffix, min = 0, max, isInt, tone = 'accent',
}: {
  label: string; value: number; onChange: (v: number) => void; tip?: string
  pct?: boolean; digits?: number; suffix?: string
  min?: number; max?: number; isInt?: boolean; tone?: 'accent' | 'danger'
}) {
  const toDisp = (v: number) => (pct ? v * 100 : v)
  const fromDisp = (d: number) => (pct ? d / 100 : d)
  const round = (d: number) => (isInt ? Math.round(d) : parseFloat(d.toFixed(digits)))
  const fmtDisp = (v: number) => String(round(toDisp(v)))
  const [focused, setFocused] = useState(false)
  const [text, setText] = useState(() => fmtDisp(value))
  useEffect(() => { if (!focused) setText(fmtDisp(value)) }, [value, focused])  // eslint-disable-line react-hooks/exhaustive-deps

  // Brief accent-ring pulse confirming an applied change. Debounced so a burst of
  // keystrokes yields one flash once typing settles, and only when the value
  // actually moved. Imperative (className) so a re-render can't cut it short.
  const inputRef = useRef<HTMLInputElement>(null)
  const flashT = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const flash = () => {
    const el = inputRef.current
    if (!el) return
    el.classList.remove('field-committed')
    void el.offsetWidth                            // reflow so the animation restarts
    el.classList.add('field-committed')
  }
  useEffect(() => () => clearTimeout(flashT.current), [])

  const commit = (raw: string) => {
    let n = parseFloat(raw)
    if (Number.isNaN(n)) return
    n = round(n)                                   // cap to `digits` decimals
    if (min != null) n = Math.max(min, n)
    if (max != null) n = Math.min(max, n)
    const out = fromDisp(n)
    onChange(out)
    if (Math.abs(out - value) > 1e-9) {            // confirm only real changes
      clearTimeout(flashT.current)
      flashT.current = setTimeout(flash, 280)
    }
  }

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ marginBottom: 6 }}>
        <FieldLabel label={suffix ? `${label} (${suffix})` : label} tip={tip} />
      </div>
      <input
        ref={inputRef}
        type="text" inputMode="decimal" aria-label={label} className="mono"
        value={text}
        onChange={(e) => { setText(e.target.value); commit(e.target.value) }}
        onFocus={(e) => { setFocused(true); e.currentTarget.select() }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            // Explicit confirm: apply, flash straight away (skip the debounce),
            // reformat, and drop focus so the change visibly "lands".
            e.preventDefault()
            commit(e.currentTarget.value)
            clearTimeout(flashT.current)
            flash()
            e.currentTarget.blur()
          }
        }}
        onBlur={() => { setFocused(false); setText(fmtDisp(value)) }}
        style={tone === 'danger' ? { color: 'var(--red)' } : undefined} />
    </div>
  )
}

/** Custom dropdown — a button + portalled popover menu styled to the design
    language (native <option> lists can't be themed). Closes on click-outside,
    Esc, or scroll; arrow keys move the active row, Enter selects. */
export function Select<T extends string>({
  value, options, onChange, ariaLabel, placeholder,
}: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; ariaLabel?: string; placeholder?: string }) {
  const btnRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const [active, setActive] = useState(-1)
  const current = options.find((o) => o.value === value)

  useLayoutEffect(() => {
    if (!open || !btnRef.current) { setRect(null); return }
    const measure = () => btnRef.current && setRect(btnRef.current.getBoundingClientRect())
    measure()
    setActive(options.findIndex((o) => o.value === value))
    const onScroll = (e: Event) => { if (!menuRef.current?.contains(e.target as Node)) setOpen(false) }
    const onResize = () => setOpen(false)
    const onDown = (e: MouseEvent) => {
      if (!btnRef.current?.contains(e.target as Node) && !menuRef.current?.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onResize)
    document.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onResize)
      document.removeEventListener('mousedown', onDown)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const choose = (v: T) => { onChange(v); setOpen(false); btnRef.current?.focus() }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { setOpen(false); return }
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setOpen(true); return }
    if (!open) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => Math.min(options.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)) }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (active >= 0) choose(options[active].value) }
  }

  // Decide whether to drop down or up given the room below the trigger.
  const below = rect ? window.innerHeight - rect.bottom > 220 || rect.top < window.innerHeight - rect.bottom : true

  return (
    <>
      <button ref={btnRef} type="button" className="select-btn" aria-haspopup="listbox" aria-expanded={open}
              aria-label={ariaLabel} onClick={() => setOpen((o) => !o)} onKeyDown={onKey}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: current ? undefined : 'var(--text-muted)' }}>
          {current?.label ?? placeholder ?? ''}
        </span>
        <svg className="select-caret" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </button>
      {open && rect && createPortal(
        <div ref={menuRef} className="select-menu" role="listbox" aria-label={ariaLabel}
             style={{
               left: rect.left, width: rect.width,
               top: below ? rect.bottom + 4 : undefined,
               bottom: below ? undefined : window.innerHeight - rect.top + 4,
             }}>
          {options.map((o, i) => (
            <button key={o.value} type="button" role="option" className="select-opt"
                    aria-selected={o.value === value} data-active={i === active}
                    onMouseEnter={() => setActive(i)} onClick={() => choose(o.value)}>
              <span>{o.label}</span>
              <svg className="select-opt-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5" /></svg>
            </button>
          ))}
        </div>,
        document.body,
      )}
    </>
  )
}

export function SelectField<T extends string>({
  label, value, options, onChange, tip,
}: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; tip?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ marginBottom: 6 }}><FieldLabel label={label} tip={tip} /></div>
      <Select value={value} options={options} onChange={onChange} ariaLabel={label} />
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
      <div style={{ marginBottom: 6 }}><FieldLabel label={label} tip={tip} /></div>
      <Segmented value={value} options={options} onChange={onChange} ariaLabel={label} />
    </div>
  )
}

export function ToggleField({
  label, checked, onChange, tip,
}: { label: string; checked: boolean; onChange: (v: boolean) => void; tip?: string }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 13, color: 'var(--text-muted)', cursor: 'pointer', marginBottom: 12 }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} style={{ width: 'auto' }} />
      {label}{tip && <InfoDot title={label} body={tip} />}
    </label>
  )
}

export function TextField({
  label, value, onChange, placeholder, hint,
}: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; hint?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={labelStyle}>{label}</label>
      <input type="text" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      {hint && <span style={{ display: 'block', fontSize: 10.5, color: 'var(--text-faint)', marginTop: 4, lineHeight: 1.4 }}>{hint}</span>}
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
