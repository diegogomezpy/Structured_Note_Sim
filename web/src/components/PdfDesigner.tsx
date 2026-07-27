import { useState } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import Icon from './Icon'
import ProofCanvas from './studio/ProofCanvas'
import ThemeBuilder from './ThemeBuilder'
import { Segmented } from './fields'
import ReportImages from './ReportImages'
import BrandConfigBar from './BrandConfigBar'
import { Card, ColorWell, Field, NumberInput, TextInput, UploadTile, grid, inputStyle } from './designerFields'
import { resolveSpec, buildTokens, writeSpec, specBase, diffSpec } from '../lib/reportTheme'
import { COVER_METRIC_KEYS, COVER_METRIC_MAX, type BrandingStudio } from '../lib/useBrandingStudio'
import type { Branding, NoteTerms } from '../api/types'

/* PDF Designer — a bespoke, from-scratch branding studio. Every input here is
   purpose-built (colour wells, upload tiles, chips) rather than reused generic
   form controls, and the whole thing is laid out as clear cards with a sticky
   live preview that renders from the SAME theme spec the PDF uses. The form
   primitives live in designerFields.tsx so the Build tab can reuse them. */


/* Whether a chosen font can actually serve its role in the PDF.

   _register_brand_fonts asks the TITLE face for a Bold and the BODY face for a
   Regular, and drops the family silently if that weight is missing — which
   looks exactly like the setting having no effect. This says so up front, and
   also names the case where the pick is a no-op because it IS the default. */
function FontStatus({ font, role, fonts, embedded }: {
  font?: string
  role: 'title' | 'body'
  fonts: { family: string; styles: string[]; builtin: boolean }[]
  embedded: number
}) {
  const { t } = useI18n()
  if (!font) return null
  const need = role === 'title' ? 'Bold' : 'Regular'
  const rf = fonts.find((x) => x.family === font)
  let msg = '', warn = false
  if (embedded > 0) {
    msg = t('font_ok_embedded')
  } else if (!rf) {
    msg = t('font_unknown'); warn = true
  } else if (rf.builtin) {
    msg = t('font_is_default')
  } else if (!rf.styles.includes(need)) {
    msg = t('font_missing_weight').replace('{w}', need); warn = true
  } else {
    msg = t('font_ok').replace('{s}', rf.styles.join(', '))
  }
  return (
    <div style={{ fontSize: 10.5, marginTop: 5, lineHeight: 1.45, color: warn ? 'var(--amber, #c9772d)' : 'var(--text-faint)' }}>
      {msg}
    </div>
  )
}

/* How far this config's theme has drifted from whatever it was authored on.

   Deliberately NOT a theme picker. The report's visual identity comes from the
   branding config — it is a property of the firm, not a style you shop for in
   the editor — so there is nothing here to choose from and no preset list. This
   only reports what your own edits have changed and lets you undo them, which
   is possible because edits are stored as `{base, ...overrides}` rather than as
   a frozen snapshot. */
function ThemeLineage({ brand, set }: {
  brand: Branding
  set: <K extends keyof Branding>(k: K, v: Branding[K]) => void
}) {
  const { t } = useI18n()
  const base = specBase(brand.report_theme)
  if (!base) return null
  const surfaces = Object.keys(diffSpec(resolveSpec(base), resolveSpec(brand.report_theme)))
  if (!surfaces.length) return null

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
      <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
        {t('brand_theme_edited').replace('{n}', String(surfaces.length))}
        <span style={{ color: 'var(--text-faint)' }}> — {surfaces.join(', ')}</span>
      </span>
      <button type="button" className="btn btn--ghost" style={{ padding: '4px 9px', fontSize: 12 }}
        onClick={() => set('report_theme', base as never)}>{t('brand_theme_reset')}</button>
    </div>
  )
}

export default function PdfDesigner({ studio, terms }: {
  studio: BrandingStudio
  terms: NoteTerms
}) {
  const { t, lang } = useI18n()
  const b = studio.brand
  const set = studio.setBrandField
  // Preview mode: Real runs the full render (genuine charts, ~slow); Fast stops
  // at the stub pass (~0.5s) for quick layout/colour work. This used to switch
  // to a hand-drawn DOM mock that constantly drifted from the PDF — deleted.
  const [realCharts, setRealCharts] = useState(true)
  // The report's default multi-series colourway (charts.py `_SERIES_COLORS`).

  return (
    <div className="brand-editor-grid fade-up" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 440px', gap: 22, alignItems: 'start' }}>
      {/* ── left: the studio ─────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        <BrandConfigBar studio={studio} />

        <Card id="identity" title={t('brand_identity')}>
          <div style={grid()}>
            <Field label={t('brand_firm')}><TextInput value={b.firm_name} onChange={(v) => set('firm_name', v)} /></Field>
            <Field label={t('brand_title')}><TextInput value={b.report_title as string} onChange={(v) => set('report_title', v)} /></Field>
            <Field label={t('brand_website')}><TextInput value={b.website} onChange={(v) => set('website', v)} placeholder="www.firm.com" /></Field>
            <Field label={t('brand_contact')}><TextInput value={b.contact} onChange={(v) => set('contact', v)} placeholder="research@firm.com" /></Field>
          </div>
          <div style={{ marginTop: 12 }}>
            <UploadTile label={t('brand_logo')} src={b.logo_base64} onPick={(f) => studio.onImage('logo_base64', f)} onClear={() => set('logo_base64', '')} />
          </div>
        </Card>

        {/* Cover sits high — it's the most-edited, most-visible surface. Its
            colour/gradient lives in Report theme → "Cover page background". */}
        <Card id="cover" title={t('brand_cover')}>
          {/* Shared with the Build tab — images are usually chosen per report. */}
          <ReportImages studio={studio} terms={terms} compact />

          {/* Cover logo & emblem placement — position/size as % of the page.
              Blank = the theme's default placement. */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 2 }}>{t('cover_placement')}</div>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, lineHeight: 1.5 }}>{t('cover_placement_hint')}</div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', margin: '2px 0 6px' }}>{t('brand_alt_logo')}</div>
            <div style={grid(110)}>
              <Field label={t('place_x')}><NumberInput value={b.cover_logo_x_pct as number | undefined} min={-20} max={100} step={1} placeholder="auto" onChange={(v) => set('cover_logo_x_pct', v as never)} /></Field>
              <Field label={t('place_y')}><NumberInput value={b.cover_logo_y_pct as number | undefined} min={-20} max={100} step={1} placeholder="auto" onChange={(v) => set('cover_logo_y_pct', v as never)} /></Field>
              <Field label={t('place_size')}><NumberInput value={b.cover_logo_size_pct as number | undefined} min={5} max={100} step={1} placeholder="43" onChange={(v) => set('cover_logo_size_pct', v as never)} /></Field>
            </div>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', margin: '12px 0 6px' }}>{t('brand_cover_sigil')}</div>
            <div style={grid(110)}>
              <Field label={t('place_x')}><NumberInput value={b.cover_sigil_x_pct as number | undefined} min={-40} max={100} step={1} placeholder="auto" onChange={(v) => set('cover_sigil_x_pct', v as never)} /></Field>
              <Field label={t('place_y')}><NumberInput value={b.cover_sigil_y_pct as number | undefined} min={-40} max={100} step={1} placeholder="auto" onChange={(v) => set('cover_sigil_y_pct', v as never)} /></Field>
              <Field label={t('place_size')}><NumberInput value={b.cover_sigil_size_pct as number | undefined} min={5} max={120} step={1} placeholder="58" onChange={(v) => set('cover_sigil_size_pct', v as never)} /></Field>
              <Field label={t('place_opacity')}><NumberInput value={b.cover_sigil_opacity as number | undefined} min={0} max={1} step={0.01} placeholder="0.22" onChange={(v) => set('cover_sigil_opacity', v as never)} /></Field>
            </div>
          </div>

          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 2 }}>{t('cover_metrics')}</div>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, lineHeight: 1.5 }}>{t('cover_metrics_hint')}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
              {COVER_METRIC_KEYS.map((k) => {
                const on = studio.coverMetricsSel.includes(k)
                const over = on && studio.coverMetricsSel.indexOf(k) >= COVER_METRIC_MAX
                return (
                  <button key={k} type="button" className="preset-pill" data-on={on}
                    title={over ? t('cover_metrics_over') : undefined} style={over ? { opacity: 0.45 } : undefined}
                    onClick={() => studio.toggleCoverMetric(k)}>{studio.metricLabel(k)}</button>
                )
              })}
            </div>
          </div>

          {/* How the cover + summary sub-lines name the underlyings. Symbols are
              compact and unambiguous; full names read better to a client who
              doesn't live on a terminal. The logo badges stay tickers either way
              — they're sized for 4–5 characters. */}
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 2 }}>{t('underlying_labels')}</div>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, lineHeight: 1.5 }}>{t('underlying_labels_hint')}</div>
            <Segmented value={(b.underlying_labels as string) === 'name' ? 'name' : 'ticker'}
                       options={[{ value: 'ticker', label: t('underlying_labels_ticker') },
                                 { value: 'name', label: t('underlying_labels_name') }]}
                       onChange={(v) => set('underlying_labels', v as never)} />
          </div>
        </Card>

        <Card id="colors" title={t('brand_colors')} desc={t('brand_palette_hint')}>
          <div style={grid(150)}>
            <ColorWell label={t('brand_primary')}   value={b.primary_color} fallback="#1a2e4a" onChange={(v) => set('primary_color', v)} />
            <ColorWell label={t('brand_accent')}    value={b.accent_color} fallback="#2563eb" onChange={(v) => set('accent_color', v)} />
            <ColorWell label={t('brand_rule')}      value={b.section_rule_color} fallback="#2563eb" onChange={(v) => set('section_rule_color', v)} />
            <ColorWell label={t('brand_panel')}     value={b.panel_color} fallback="#eaf1f8" onChange={(v) => set('panel_color', v)} />
            <ColorWell label={t('brand_secondary')} value={b.chart_secondary_color} fallback="#c69426" onChange={(v) => set('chart_secondary_color', v)} />
            <ColorWell label={t('brand_sidebar')}   value={b.sidebar_bar_color as string} fallback={b.primary_color ?? '#1a2e4a'} onChange={(v) => set('sidebar_bar_color', v)} />
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 10, lineHeight: 1.5 }}>{t('brand_colors_charts_hint')}</div>
        </Card>

        {/* No chart-colour card: every figure is themed from the report palette
            and each trace carries a semantic colour (autocall / coupon / knock-in
            / outcome), so per-chart colour/size overrides had no visible effect.
            The controls were removed rather than left as inert knobs. */}

        <Card id="theme" title={t('brand_theme')} desc={t('brand_theme_hint')}>
          <ThemeLineage brand={b} set={set} />
          <ThemeBuilder spec={resolveSpec(b.report_theme) as Record<string, unknown>} tokens={buildTokens(b)}
            onChange={(s) => set('report_theme', writeSpec(b.report_theme, s as never) as never)} />
        </Card>

        <Card id="typography" title={t('brand_typography')}>
          <div style={grid()}>
            {(['title_font', 'body_font'] as const).map((f, i) => {
              const filesKey = (i === 0 ? 'title_font_files' : 'body_font_files') as 'title_font_files' | 'body_font_files'
              const ref = i === 0 ? studio.refs.titleFont : studio.refs.bodyFont
              return (
                <Field key={f} label={i === 0 ? t('brand_title_font') : t('brand_body_font')}>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <select value={studio.reportFonts.some((rf) => rf.family === b[f]) ? (b[f] as string) : ''}
                      onChange={(e) => set(f, e.target.value)}
                      style={{ ...inputStyle, width: 'auto', flexShrink: 0, minWidth: 110 }}>
                      <option value="">{t('brand_font_custom')}</option>
                      {studio.reportFonts.map((rf) => (
                        <option key={rf.file} value={rf.family}>{rf.family}</option>
                      ))}
                    </select>
                    <TextInput value={b[f] as string} onChange={(v) => set(f, v)} placeholder="IBM Plex Sans" />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
                    <button type="button" className="btn btn--ghost" style={{ padding: '5px 9px', fontSize: 11.5 }} onClick={() => ref.current?.click()}><Icon name="upload" size={12} /> {t('brand_embed_fonts')}</button>
                    {studio.fontCount(filesKey) > 0 && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t('brand_fonts_n', { n: studio.fontCount(filesKey) })}</span>}
                    <input ref={ref} type="file" accept=".ttf,.otf" multiple style={{ display: 'none' }} onChange={(e) => { studio.onFontFiles(filesKey, e.target.files); e.target.value = '' }} />
                  </div>
                  {/* Say whether the pick will actually reach the PDF. The report
                      asks a title face for Bold and a body face for Regular; a
                      family missing that weight is silently ignored, which is
                      indistinguishable from "the setting does nothing". */}
                  <FontStatus font={b[f] as string} role={i === 0 ? 'title' : 'body'}
                    fonts={studio.reportFonts} embedded={studio.fontCount(filesKey)} />
                </Field>
              )
            })}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 8 }}>{t('brand_font_hint')}</div>
        </Card>

        <Card id="watermark" title={t('brand_watermark')} desc={t('brand_watermark_hint')}>
          {/* The watermark: an uploaded image, else the theme's own mark
              (e.g. CADIEM's hexagons). One appearance, applied identically on
              every surface; the "Show on" toggles are the only on/off. */}
          <UploadTile label={t('brand_watermark_img')} src={b.watermark_base64 as string} dark
            onPick={(f) => studio.onImage('watermark_base64', f)} onClear={() => set('watermark_base64', '')} />

          <div style={{ ...grid(150), marginTop: 14 }}>
            <Field label={t('wm_opacity')}>
              <NumberInput value={b.watermark_opacity as number | undefined} min={0} max={1} step={0.01}
                placeholder="0.13" onChange={(v) => set('watermark_opacity', v as never)} />
            </Field>
            <Field label={t('wm_scale')}>
              <NumberInput value={b.watermark_scale as number | undefined} min={0.05} max={1} step={0.02}
                placeholder="0.58" onChange={(v) => set('watermark_scale', v as never)} />
            </Field>
          </div>

          <div style={{ marginTop: 12 }}>
            <span style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 5 }}>{t('wm_anchor')}</span>
            <Segmented value={(b.watermark_anchor as string) ?? 'right'} ariaLabel={t('wm_anchor')}
              options={[{ value: 'left', label: t('wm_left') }, { value: 'center', label: t('wm_center') }, { value: 'right', label: t('wm_right') }]}
              onChange={(v) => set('watermark_anchor', v as never)} />
          </div>

          {/* The ONE gate. Uncheck every surface to turn the watermark off. */}
          <div style={{ marginTop: 14 }}>
            <span style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>{t('wm_places')}</span>
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              {(['masthead', 'divider', 'void', 'cover'] as const).map((k) => {
                const sel = (b.watermark_places as string[] | undefined) ?? ['masthead', 'divider', 'void', 'cover']
                const on = sel.includes(k)
                return (
                  <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5, color: 'var(--text-muted)', cursor: 'pointer' }}>
                    <input type="checkbox" checked={on} style={{ width: 'auto' }}
                      onChange={() => set('watermark_places',
                        (on ? sel.filter((x) => x !== k) : [...sel, k]) as never)} />
                    {t(`wm_place_${k}`)}
                  </label>
                )
              })}
            </div>
            <span style={{ display: 'block', fontSize: 10.5, color: 'var(--text-faint)', marginTop: 6, lineHeight: 1.4 }}>{t('wm_places_hint')}</span>
          </div>
        </Card>

        <Card id="legal" title={t('brand_legal')}>
          <Field label={t('brand_footer')}><TextInput value={b.footer_note} onChange={(v) => set('footer_note', v)} /></Field>
          <div style={{ marginTop: 12 }}>
            <Field label={t('brand_disclaimer')}>
              <textarea value={b.disclaimer_body ?? ''} onChange={(e) => set('disclaimer_body', e.target.value)}
                style={{ ...inputStyle, minHeight: 84, resize: 'vertical', lineHeight: 1.5 }} />
            </Field>
          </div>
        </Card>
      </div>

      {/* ── right: the preview column ──────────────────────────────────────
          The proof IS the PDF (server-rendered), so it cannot drift. Real vs
          Fast only decides whether the genuine (slow) charts are drawn. */}
      <div className="brand-preview-col" style={{ position: 'sticky', top: 12, display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 'calc(100vh - 24px)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
            {t('proof_title')}
          </div>
          <div style={{ flex: 1, minWidth: 0, maxWidth: 190, marginLeft: 'auto' }}>
            <Segmented value={realCharts ? 'real' : 'fast'} ariaLabel={t('proof_mode')}
              options={[{ value: 'real', label: t('proof_mode_real') }, { value: 'fast', label: t('proof_mode_fast') }]}
              onChange={(v) => setRealCharts(v === 'real')} />
          </div>
        </div>
        <div style={{ overflowY: 'auto', overflowX: 'hidden', flex: 1, borderRadius: 12, paddingRight: 2 }}>
          <ProofCanvas brand={b} terms={terms} lang={lang} zoom={0.78} realCharts={realCharts} />
        </div>
        <div style={{ fontSize: 10.5, color: 'var(--text-faint)', lineHeight: 1.45 }}>
          {realCharts ? t('proof_hint') : t('proof_hint_fast')}
        </div>
      </div>
    </div>
  )
}
