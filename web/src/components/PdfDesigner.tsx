import { useI18n } from '../i18n/I18nProvider'
import Icon from './Icon'
import BrandPreview from './BrandPreview'
import ThemeBuilder from './ThemeBuilder'
import ReportImages from './ReportImages'
import FolderConnect from './FolderConnect'
import { Card, ColorWell, Field, TextInput, UploadTile, grid, inputStyle } from './designerFields'
import { resolveSpec, buildTokens } from '../lib/reportTheme'
import { COVER_METRIC_KEYS, COVER_METRIC_MAX, FONT_PRESETS, type BrandingStudio } from '../lib/useBrandingStudio'
import type { NoteTerms } from '../api/types'

/* PDF Designer — a bespoke, from-scratch branding studio. Every input here is
   purpose-built (colour wells, upload tiles, chips) rather than reused generic
   form controls, and the whole thing is laid out as clear cards with a sticky
   live preview that renders from the SAME theme spec the PDF uses. The form
   primitives live in designerFields.tsx so the Build tab can reuse them. */


export default function PdfDesigner({ studio, terms }: { studio: BrandingStudio; terms: NoteTerms }) {
  const { t } = useI18n()
  const b = studio.brand
  const set = studio.setBrandField
  const noteName = terms?.name

  return (
    <div className="brand-editor-grid fade-up" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 440px', gap: 22, alignItems: 'start' }}>
      {/* ── left: the studio ─────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        {/* config bar */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
          <button className="btn btn--primary" style={{ padding: '7px 12px' }} onClick={studio.newBranding}
            title={t('brand_new_hint')}><Icon name="plus" size={13} /> {t('brand_new')}</button>
          <select value="" onChange={(e) => {
            const v = e.target.value
            if (v === '__new') { studio.newBranding(); return }
            if (v.startsWith('local:')) { const f = studio.brandFolder.files.find((x) => `local:${x.name}` === v); if (f) { studio.setBrandLocalName(f.name); studio.applyBranding(f.raw as Record<string, unknown>) } }
            else if (v) studio.loadPreset(v)
          }} style={{ ...inputStyle, width: 'auto', minWidth: 180 }}>
            <option value="">{t('brand_preset_ph')}</option>
            <option value="__new">{t('brand_new')}</option>
            {studio.brandFolder.files.map((f) => <option key={f.name} value={`local:${f.name}`}>{f.name} {t('folder_tag')}</option>)}
            {studio.presets.map((p) => <option key={p.file} value={p.file}>{p.firm_name}</option>)}
          </select>
          {/* config name — used as the saved filename */}
          <input type="text" value={studio.brandLocalName ?? ''} placeholder={t('brand_config_name')}
            onChange={(e) => studio.setBrandLocalName(e.target.value || null)}
            style={{ ...inputStyle, width: 'auto', minWidth: 150 }} />
          <FolderConnect fld={studio.brandFolder} />
          <div style={{ flex: 1 }} />
          <button className="btn" style={{ padding: '7px 12px' }} onClick={() => studio.refs.cfg.current?.click()}><Icon name="upload" size={13} /> {t('brand_upload_cfg_btn')}</button>
          <button className="btn" style={{ padding: '7px 12px' }} onClick={studio.downloadBranding}><Icon name="download" size={13} /> {t('brand_save_cfg_btn')}</button>
          {studio.brandFolder.canSave && (
            <button className="btn" style={{ padding: '7px 12px' }} disabled={studio.brandSaving} onClick={studio.saveBrandingToFolder}>
              <Icon name={studio.brandSaving ? 'spinner' : 'save'} size={13} /> {t('brand_save_to_folder_btn')}
            </button>
          )}
          <input ref={studio.refs.cfg} type="file" accept="application/json,.json" style={{ display: 'none' }}
                 onChange={(e) => { studio.onUploadBranding(e.target.files?.[0]); e.target.value = '' }} />
        </div>
        {studio.error && <div style={{ fontSize: 12, color: 'var(--red, #c0392b)' }}>{studio.error}</div>}

        <Card title={t('brand_identity')}>
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

        <Card title={t('brand_colors')} desc={t('brand_palette_hint')}>
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

        <Card title={t('brand_theme')} desc={t('brand_theme_hint')}>
          <ThemeBuilder spec={resolveSpec(b.report_theme) as Record<string, unknown>} tokens={buildTokens(b)}
            onChange={(s) => set('report_theme', s as never)} />
        </Card>

        <Card title={t('brand_typography')}>
          <div style={grid()}>
            {(['title_font', 'body_font'] as const).map((f, i) => {
              const filesKey = (i === 0 ? 'title_font_files' : 'body_font_files') as 'title_font_files' | 'body_font_files'
              const ref = i === 0 ? studio.refs.titleFont : studio.refs.bodyFont
              return (
                <Field key={f} label={i === 0 ? t('brand_title_font') : t('brand_body_font')}>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <select value={FONT_PRESETS.includes(b[f] as string) ? (b[f] as string) : ''}
                      onChange={(e) => set(f, e.target.value)}
                      style={{ ...inputStyle, width: 'auto', flexShrink: 0, minWidth: 92 }}>
                      <option value="">{t('brand_font_custom')}</option>
                      {FONT_PRESETS.map((fn) => <option key={fn} value={fn}>{fn}</option>)}
                    </select>
                    <TextInput value={b[f] as string} onChange={(v) => set(f, v)} placeholder="IBM Plex Sans" />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
                    <button type="button" className="btn btn--ghost" style={{ padding: '5px 9px', fontSize: 11.5 }} onClick={() => ref.current?.click()}><Icon name="upload" size={12} /> {t('brand_embed_fonts')}</button>
                    {studio.fontCount(filesKey) > 0 && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t('brand_fonts_n', { n: studio.fontCount(filesKey) })}</span>}
                    <input ref={ref} type="file" accept=".ttf,.otf" multiple style={{ display: 'none' }} onChange={(e) => { studio.onFontFiles(filesKey, e.target.files); e.target.value = '' }} />
                  </div>
                </Field>
              )
            })}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 8 }}>{t('brand_font_hint')}</div>
        </Card>

        <Card title={t('brand_cover')}>
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

        <Card title={t('brand_watermark')} desc={t('brand_watermark_hint')}>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap' }}>
            <UploadTile label={t('brand_watermark')} src={b.watermark_base64 as string} dark
              onPick={(f) => studio.onImage('watermark_base64', f)} onClear={() => set('watermark_base64', '')} />
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--text-muted)', cursor: 'pointer', paddingBottom: 6 }}>
              <input type="checkbox" checked={b.watermark_enabled !== false}
                onChange={(e) => set('watermark_enabled', e.target.checked as never)} style={{ width: 'auto' }} />
              {t('brand_watermark_toggle')}
            </label>
          </div>
        </Card>

        <Card title={t('brand_legal')}>
          <Field label={t('brand_footer')}><TextInput value={b.footer_note} onChange={(v) => set('footer_note', v)} /></Field>
          <div style={{ marginTop: 12 }}>
            <Field label={t('brand_disclaimer')}>
              <textarea value={b.disclaimer_body ?? ''} onChange={(e) => set('disclaimer_body', e.target.value)}
                style={{ ...inputStyle, minHeight: 84, resize: 'vertical', lineHeight: 1.5 }} />
            </Field>
          </div>
        </Card>
      </div>

      {/* ── right: sticky live preview (scrolls internally: 4 pages) ───── */}
      <div className="brand-preview-col" style={{ position: 'sticky', top: 12, display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 'calc(100vh - 24px)' }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-faint)' }}>{t('brand_preview')}</div>
        <div style={{ overflowY: 'auto', overflowX: 'hidden', flex: 1, borderRadius: 12, paddingRight: 2 }}>
          <BrandPreview brand={b} noteName={noteName} terms={terms}
                        coverMetrics={studio.coverMetricsSel} metricLabel={studio.metricLabel} />
        </div>
        <div style={{ fontSize: 10.5, color: 'var(--text-faint)', lineHeight: 1.45 }}>{t('brand_preview_hint')}</div>
      </div>
    </div>
  )
}
