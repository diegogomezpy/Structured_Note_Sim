import { useI18n } from '../i18n/I18nProvider'
import Icon from './Icon'
import BrandPreview from './BrandPreview'
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

export default function PdfDesigner({ studio, terms, preview = 'proof', onPreviewChange = () => {} }: {
  studio: BrandingStudio
  terms: NoteTerms
  preview?: 'proof' | 'mock'
  onPreviewChange?: (v: 'proof' | 'mock') => void
}) {
  const { t, lang } = useI18n()
  const b = studio.brand
  const set = studio.setBrandField
  const noteName = terms?.name
  // The report's default multi-series colourway (charts.py `_SERIES_COLORS`).
  const DEFAULT_SERIES = ['#2563eb', '#1a2e4a', '#60a5fa', '#0891b2', '#7c3aed', '#0d9488']
  const seriesColors = (b.chart_series_colors as string[] | undefined) ?? DEFAULT_SERIES

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

        <Card id="charts" title={t('brand_charts')} desc={t('brand_charts_hint')}>
          <div style={grid(150)}>
            <ColorWell label={t('chart_grid')}  value={b.chart_grid_color}  fallback="#f1f5f9" onChange={(v) => set('chart_grid_color', v)} />
            <ColorWell label={t('chart_axis')}  value={b.chart_axis_color}  fallback="#e5e7eb" onChange={(v) => set('chart_axis_color', v)} />
            <ColorWell label={t('chart_label')} value={b.chart_label_color} fallback="#6b7280" onChange={(v) => set('chart_label_color', v)} />
            <ColorWell label={t('chart_text')}  value={b.chart_text_color}  fallback="#1a2e4a" onChange={(v) => set('chart_text_color', v)} />
            <ColorWell label={t('chart_bg')}    value={b.chart_bg_color}    fallback="#ffffff" onChange={(v) => set('chart_bg_color', v)} />
          </div>
          <div style={{ ...grid(150), marginTop: 12 }}>
            <Field label={t('chart_font_size')}>
              <input type="number" min={6} max={20} step={0.5} placeholder="12"
                value={b.chart_font_size != null ? String(b.chart_font_size) : ''}
                onChange={(e) => set('chart_font_size', e.target.value)} style={inputStyle} />
            </Field>
            <Field label={t('chart_band_opacity')}>
              <input type="number" min={0} max={3} step={0.05} placeholder="1.0"
                value={b.chart_band_opacity != null ? String(b.chart_band_opacity) : ''}
                onChange={(e) => set('chart_band_opacity', e.target.value)} style={inputStyle} />
            </Field>
            <Field label={t('chart_line_width')}>
              <input type="number" min={0.2} max={4} step={0.1} placeholder="1.0"
                value={b.chart_line_width != null ? String(b.chart_line_width) : ''}
                onChange={(e) => set('chart_line_width', e.target.value)} style={inputStyle} />
            </Field>
          </div>
          {/* Multi-series colourway — the per-underlying line/slice colours. */}
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>{t('chart_series')}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              {seriesColors.map((c, i) => (
                <input key={i} type="color" value={c} aria-label={`${t('chart_series')} ${i + 1}`}
                  onChange={(e) => {
                    const next = [...seriesColors]; next[i] = e.target.value
                    set('chart_series_colors', next as never)
                  }}
                  style={{ width: 34, height: 30, padding: 0, border: '1px solid var(--border-strong)', borderRadius: 7, background: 'none', cursor: 'pointer' }} />
              ))}
              {seriesColors.length > 2 && (
                <button type="button" className="btn btn--ghost" style={{ padding: '4px 9px', fontSize: 12 }}
                  onClick={() => set('chart_series_colors', seriesColors.slice(0, -1) as never)}>−</button>
              )}
              {seriesColors.length < 8 && (
                <button type="button" className="btn btn--ghost" style={{ padding: '4px 9px', fontSize: 12 }}
                  onClick={() => set('chart_series_colors', [...seriesColors, '#0891b2'] as never)}>+</button>
              )}
              {b.chart_series_colors != null && (
                <button type="button" className="btn btn--ghost" style={{ padding: '4px 9px', fontSize: 12 }}
                  onClick={() => set('chart_series_colors', undefined as never)}>{t('chart_series_reset')}</button>
              )}
            </div>
          </div>
        </Card>

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

        <Card id="cover" title={t('brand_cover')}>
          {/* Shared with the Build tab — images are usually chosen per report. */}
          <ReportImages studio={studio} terms={terms} compact />
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
        </Card>

        <Card id="watermark" title={t('brand_watermark')} desc={t('brand_watermark_hint')}>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
            <UploadTile label={t('brand_watermark_img')} src={b.watermark_base64 as string} dark
              onPick={(f) => studio.onImage('watermark_base64', f)} onClear={() => set('watermark_base64', '')} />
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--text-muted)', cursor: 'pointer', paddingBottom: 6 }}>
              <input type="checkbox" checked={b.watermark_enabled !== false}
                onChange={(e) => set('watermark_enabled', e.target.checked as never)} style={{ width: 'auto' }} />
              {t('brand_watermark_toggle')}
            </label>
          </div>

          {/* Appearance — one place, applied wherever the mark is drawn. */}
          <div style={{ ...grid(150), marginTop: 14 }}>
            <Field label={t('wm_opacity')}>
              <NumberInput value={b.watermark_opacity as number | undefined} min={0} max={1} step={0.01}
                placeholder="0.13" onChange={(v) => set('watermark_opacity', v as never)} />
            </Field>
            <Field label={t('wm_scale')}>
              <NumberInput value={b.watermark_scale as number | undefined} min={0.05} max={1} step={0.02}
                placeholder="0.58" onChange={(v) => set('watermark_scale', v as never)} />
            </Field>
            <Field label={t('wm_inset')}>
              <NumberInput value={b.watermark_inset as number | undefined} min={0} max={100} step={1}
                placeholder="auto" onChange={(v) => set('watermark_inset', v as never)} />
            </Field>
          </div>

          <div style={{ marginTop: 12 }}>
            <span style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 5 }}>{t('wm_anchor')}</span>
            <Segmented value={(b.watermark_anchor as string) ?? 'right'} ariaLabel={t('wm_anchor')}
              options={[{ value: 'left', label: t('wm_left') }, { value: 'center', label: t('wm_center') }, { value: 'right', label: t('wm_right') }]}
              onChange={(v) => set('watermark_anchor', v as never)} />
          </div>

          {/* Where it appears. Empty = wherever the theme draws one. */}
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
          Two implementations live here for now. `proof` renders the real PDF
          server-side and is the one that cannot drift; `mock` is the original
          hand-drawn DOM approximation, kept until the proof's latency has been
          measured on the deploy rather than a dev machine. */}
      <div className="brand-preview-col" style={{ position: 'sticky', top: 12, display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 'calc(100vh - 24px)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-faint)', whiteSpace: 'nowrap' }}>
            {preview === 'proof' ? t('proof_title') : t('brand_preview')}
          </div>
          <div style={{ flex: 1, minWidth: 0, maxWidth: 190, marginLeft: 'auto' }}>
            <Segmented value={preview} ariaLabel={t('proof_mode')}
              options={[{ value: 'proof', label: t('proof_mode_real') }, { value: 'mock', label: t('proof_mode_fast') }]}
              onChange={(v) => onPreviewChange(v as 'proof' | 'mock')} />
          </div>
        </div>
        <div style={{ overflowY: 'auto', overflowX: 'hidden', flex: 1, borderRadius: 12, paddingRight: 2 }}>
          {preview === 'proof' ? (
            <ProofCanvas brand={b} terms={terms} lang={lang} zoom={0.78} />
          ) : (
            <BrandPreview brand={b} noteName={noteName} terms={terms} reportFonts={studio.reportFonts}
                          coverMetrics={studio.coverMetricsSel} metricLabel={studio.metricLabel} />
          )}
        </div>
        <div style={{ fontSize: 10.5, color: 'var(--text-faint)', lineHeight: 1.45 }}>
          {preview === 'proof' ? t('proof_hint') : t('brand_preview_hint')}
        </div>
      </div>
    </div>
  )
}
