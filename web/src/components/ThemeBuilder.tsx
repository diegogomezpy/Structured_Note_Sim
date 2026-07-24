import { useState } from 'react'
import { Segmented } from './fields'
import { NumberInput } from './designerFields'
import {
  resolveColor, rgbToHex, type Tokens,
} from '../lib/reportTheme'

/* Freeform theme builder — edits a declarative theme spec (the same one the PDF
   and the live preview consume). Friendly per-surface controls for the common
   knobs (shape / fill / gradient / watermark) plus a raw-JSON editor for the
   full spec (geometry and anything else). Writes to branding.report_theme. */

type Spec = Record<string, unknown>
type Any = Record<string, unknown>

function setIn(o: unknown, path: (string | number)[], v: unknown): unknown {
  if (!path.length) return v
  const [k, ...rest] = path
  const base: Any = Array.isArray(o) ? [...(o as unknown[])] as unknown as Any : { ...(o as Any) }
  base[k as string] = setIn((base as Any)[k as string], rest, v)
  return base
}

const lbl = { fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, display: 'block', fontWeight: 600 } as const
const row = { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' as const }

// ── plain colour well: a native picker + hex, no token presets ───────────────
// Writes an absolute { hex } — same "just choose the colour" model as the
// Colours section, used for fills / gradient stops.
function ColorWell({ value, tokens, onChange }: { value: unknown; tokens: Tokens; onChange: (v: unknown) => void }) {
  const hex = rgbToHex(resolveColor(value as never, tokens))
  return (
    <div style={row}>
      <input type="color" value={hex} aria-label="Colour" onChange={(e) => onChange({ hex: e.target.value })}
        style={{ width: 32, height: 28, padding: 0, border: '1px solid var(--border-strong, var(--border))', borderRadius: 7, background: 'none', cursor: 'pointer', flexShrink: 0 }} />
      <input type="text" value={hex}
        onChange={(e) => { const v = e.target.value.trim(); const h = v.startsWith('#') ? v : '#' + v; if (/^#[0-9a-fA-F]{0,6}$/.test(h)) onChange({ hex: h }) }}
        style={{ width: 96, fontSize: 12, fontFamily: 'var(--font-mono, monospace)', padding: '6px 8px', borderRadius: 7, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)' }} />
    </div>
  )
}

// ── fill: solid | linear | radial (with gradient stops) ─────────────────────
function FillControl({ value, tokens, onChange }: { value: unknown; tokens: Tokens; onChange: (v: unknown) => void }) {
  const fill = (value as Any) || { type: 'solid', color: 'ink' }
  const type = (fill.type as string) || 'solid'
  const stops = (fill.stops as Any[]) || []
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <Segmented value={type} ariaLabel="Fill type"
        options={[{ value: 'solid', label: 'Solid' }, { value: 'linear', label: 'Gradient' }, { value: 'radial', label: 'Radial' }]}
        onChange={(t) => {
          if (t === 'solid') onChange({ type: 'solid', color: fill.color ?? (stops[0] as Any)?.color ?? 'ink' })
          else onChange({ type: t, angle: fill.angle ?? 90, stops: stops.length ? stops : [{ color: fill.color ?? 'ink' }, { color: 'teal' }] })
        }} />
      {type === 'solid' ? (
        <ColorWell value={fill.color} tokens={tokens} onChange={(c) => onChange({ ...fill, color: c })} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {type === 'linear' && (
            <label style={{ ...row, fontSize: 11.5, color: 'var(--text-muted)' }}>
              Angle
              <NumberInput value={Number(fill.angle ?? 90)} step={5} min={0} max={360}
                onChange={(v) => onChange({ ...fill, angle: v })} style={{ width: 64, fontSize: 12, padding: '4px 6px', borderRadius: 7 }} />°
            </label>
          )}
          {stops.map((s, i) => (
            <div key={i} style={row}>
              <ColorWell value={(s as Any).color} tokens={tokens} onChange={(c) => onChange(setIn(fill, ['stops', i, 'color'], c))} />
              {stops.length > 2 && (
                <button type="button" className="btn btn--ghost" style={{ padding: '2px 7px', fontSize: 12 }}
                  onClick={() => onChange({ ...fill, stops: stops.filter((_, j) => j !== i) })}>×</button>
              )}
            </div>
          ))}
          <button type="button" className="btn btn--ghost" style={{ padding: '3px 9px', fontSize: 11.5, alignSelf: 'flex-start' }}
            onClick={() => onChange({ ...fill, stops: [...stops, { color: 'lime' }] })}>+ colour stop</button>
        </div>
      )}
    </div>
  )
}

function ShapeControl({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const shape = (value as Any) || { kind: 'rounded' }
  const kind = (shape.kind as string) || 'rounded'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <Segmented value={kind} ariaLabel="Shape"
        options={[{ value: 'chamfer', label: 'Chamfer' }, { value: 'rounded', label: 'Rounded' }, { value: 'square', label: 'Square' }]}
        onChange={(k) => {
          if (k === 'chamfer') onChange({ kind: 'chamfer', c: shape.c ?? 5, q: shape.q ?? 1.5, r: shape.r ?? 4 })
          else if (k === 'rounded') onChange({ kind: 'rounded', radius: shape.radius ?? 3 })
          else onChange({ kind: 'square' })
        }} />
      {kind === 'chamfer' && (
        <label style={{ ...row, fontSize: 11.5, color: 'var(--text-muted)' }}>Cut
          <NumberInput value={Number(shape.c ?? 5)} step={0.5} min={0} max={40}
            onChange={(v) => onChange({ ...shape, c: v })} style={{ width: 64, fontSize: 12, padding: '4px 6px', borderRadius: 7 }} />mm</label>
      )}
      {kind === 'rounded' && (
        <label style={{ ...row, fontSize: 11.5, color: 'var(--text-muted)' }}>Radius
          <NumberInput value={Number(shape.radius ?? 3)} step={0.5} min={0} max={40}
            onChange={(v) => onChange({ ...shape, radius: v })} style={{ width: 64, fontSize: 12, padding: '4px 6px', borderRadius: 7 }} />mm</label>
      )}
    </div>
  )
}

function Group({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '11px 12px' }}>
      <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{title}</div>
      {note && <div style={{ fontSize: 10.5, color: 'var(--text-faint)', lineHeight: 1.45, marginTop: 4 }}>{note}</div>}
      <div style={{ display: 'flex', flexDirection: 'column', marginTop: 9 }}>{children}</div>
    </div>
  )
}

/* One labelled setting. Every value in a group used to be a bare stack of divs,
   so a shape control and the fill beneath it ran together with nothing marking
   where one setting ended and the next began. A hairline and a consistent label
   column give each its own line. */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ paddingTop: 9, marginTop: 9, borderTop: '1px solid var(--border)' }}>
      <span style={lbl}>{label}</span>
      {children}
    </div>
  )
}

export default function ThemeBuilder({ spec, tokens, onChange }: { spec: Spec; tokens: Tokens; onChange: (s: Spec) => void }) {
  const [json, setJson] = useState<string | null>(null)   // null = follow structured state
  const [jsonErr, setJsonErr] = useState('')
  const upd = (path: (string | number)[], v: unknown) => onChange(setIn(spec, path, v) as Spec)

  const cover = (spec.cover as Any) || {}
  const masthead = (spec.cover_masthead as Any) || {}
  const divider = (spec.divider as Any) || {}
  const chip = ((spec.secondary_head as Any)?.chip as Any) || {}
  const header = (spec.header as Any) || {}
  const dividerStyle = (divider.style as string) || 'banner'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Group title="Cover page background" note="Shown on the full-bleed cover & disclaimer pages, behind any cover photo.">
        <Row label="Fill">
          <FillControl value={cover.fill ?? { type: 'solid', color: 'primary' }} tokens={tokens} onChange={(v) => upd(['cover', 'fill'], v)} /></Row>
      </Group>

      <Group title="Cover masthead">
        <Row label="Shape"><ShapeControl value={masthead.shape} onChange={(v) => upd(['cover_masthead', 'shape'], v)} /></Row>
        <Row label="Fill"><FillControl value={masthead.fill} tokens={tokens} onChange={(v) => upd(['cover_masthead', 'fill'], v)} /></Row>
      </Group>

      <Group title="Chapter divider">
        <Row label="Style">
          <Segmented value={dividerStyle} ariaLabel="Divider style"
            options={[{ value: 'banner', label: 'Dark banner' }, { value: 'editorial', label: 'Editorial' }]}
            onChange={(v) => upd(['divider', 'style'], v)} />
        </Row>
        {dividerStyle === 'banner' && (
          <>
            <Row label="Shape"><ShapeControl value={divider.shape} onChange={(v) => upd(['divider', 'shape'], v)} /></Row>
            <Row label="Fill"><FillControl value={divider.fill} tokens={tokens} onChange={(v) => upd(['divider', 'fill'], v)} /></Row>
          </>
        )}
      </Group>

      <Group title="Section number-chip">
        <Row label="Shape"><ShapeControl value={chip.shape} onChange={(v) => upd(['secondary_head', 'chip', 'shape'], v)} /></Row>
        <Row label="Fill"><FillControl value={chip.fill} tokens={tokens} onChange={(v) => upd(['secondary_head', 'chip', 'fill'], v)} /></Row>
      </Group>

      <Group title="Running header" note="The rule and accent tick at the top of every interior page.">
        <Row label="Rule colour"><ColorWell value={(header.rule as Any)?.color} tokens={tokens} onChange={(v) => upd(['header', 'rule', 'color'], v)} /></Row>
        <Row label="Accent tick">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <label style={{ ...row, fontSize: 12.5, color: 'var(--text-muted)', cursor: 'pointer' }}>
              <input type="checkbox" checked={!!header.tick} style={{ width: 'auto' }}
                onChange={(e) => upd(['header', 'tick'], e.target.checked ? { color: 'lime', w: 15, h: 0.8, y: 16.1, radius: 0.4 } : null)} />
              Show the tick
            </label>
            {!!header.tick && (
              <ColorWell value={(header.tick as Any)?.color} tokens={tokens}
                onChange={(v) => upd(['header', 'tick', 'color'], v)} />
            )}
          </div>
        </Row>
      </Group>

      <Group title="Empty space" note="What fills the gap when a section ends short of the page.">
        <Row label="Decoration">
          <Segmented value={((spec.void as Any)?.decoration as string) || 'none'} ariaLabel="Void decoration"
            options={[{ value: 'watermark', label: 'Watermark' }, { value: 'accentKeyline', label: 'Keyline' }, { value: 'none', label: 'None' }]}
            onChange={(v) => upd(['void', 'decoration'], v)} />
        </Row>
      </Group>

      {/* raw-JSON escape hatch — full freeform, incl. geometry */}
      <details>
        <summary style={{ cursor: 'pointer', fontSize: 11.5, fontWeight: 600, color: 'var(--text-muted)' }}>Raw spec (JSON)</summary>
        <textarea
          value={json ?? JSON.stringify(spec, null, 2)}
          onChange={(e) => {
            setJson(e.target.value)
            try { const parsed = JSON.parse(e.target.value); setJsonErr(''); onChange(parsed) }
            catch (err) { setJsonErr(String((err as Error).message)) }
          }}
          onBlur={() => setJson(null)}
          spellCheck={false}
          style={{ width: '100%', minHeight: 180, marginTop: 8, fontFamily: 'var(--font-mono, monospace)', fontSize: 11.5, lineHeight: 1.5, padding: '9px 11px', borderRadius: 9, border: `1px solid ${jsonErr ? 'var(--red, #c0392b)' : 'var(--border)'}`, background: 'var(--surface)', color: 'var(--text)' }} />
        {jsonErr && <div style={{ fontSize: 11, color: 'var(--red, #c0392b)', marginTop: 4 }}>Invalid JSON: {jsonErr}</div>}
      </details>
    </div>
  )
}
