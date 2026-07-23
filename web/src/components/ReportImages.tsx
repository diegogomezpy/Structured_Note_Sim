import { useI18n } from '../i18n/I18nProvider'
import Icon from './Icon'
import CoverPhotoPicker from './CoverPhotoPicker'
import { Field, UploadTile, grid, inputStyle } from './designerFields'
import type { BrandingStudio } from '../lib/useBrandingStudio'
import type { NoteTerms } from '../api/types'

/* Every image the report can carry, in one place. Rendered BOTH in the PDF
   Designer (as part of the brand config) and on the Build tab — pictures tend to
   be chosen per report, unlike the durable design/identity settings, so you
   shouldn't have to leave Build to swap a cover photo. Both instances edit the
   same shared branding state. */
export default function ReportImages({ studio, terms, compact }: {
  studio: BrandingStudio; terms: NoteTerms; compact?: boolean
}) {
  const { t } = useI18n()
  const b = studio.brand
  const set = studio.setBrandField

  return (
    <div>
      <div style={grid()}>
        <UploadTile label={t('brand_cover_image')} src={b.cover_image_base64 as string} dark
          onPick={(f) => studio.onImage('cover_image_base64', f)} onClear={() => set('cover_image_base64', '')} />
        <UploadTile label={t('brand_back_image')} src={b.back_image_base64 as string} dark
          onPick={(f) => studio.onImage('back_image_base64', f)} onClear={() => set('back_image_base64', '')} />
        <UploadTile label={t('brand_alt_logo')} src={b.cover_logo_base64} dark
          onPick={(f) => studio.onImage('cover_logo_base64', f)} onClear={() => set('cover_logo_base64', '')} />
        <UploadTile label={t('brand_cover_sigil')} src={b.cover_sigil_base64} dark
          onPick={(f) => studio.onImage('cover_sigil_base64', f)} onClear={() => set('cover_sigil_base64', '')} />
        <UploadTile label={t('brand_watermark')} src={b.watermark_base64 as string} dark
          onPick={(f) => studio.onImage('watermark_base64', f)} onClear={() => set('watermark_base64', '')} />
        {/* The cover's colour is set once, under Report theme → "Cover page
            background" (solid/gradient/radial). This is only how strongly that
            fill tints a cover PHOTO — there is no second colour control. */}
        <Field label={t('brand_overlay_opacity')}>
          <input type="number" min={0} max={1} step={0.05} placeholder="0.55"
            value={b.cover_overlay_opacity != null ? String(b.cover_overlay_opacity) : ''}
            onChange={(e) => set('cover_overlay_opacity', e.target.value)} style={inputStyle} />
          <span style={{ display: 'block', fontSize: 10.5, color: 'var(--text-faint)', marginTop: 4, lineHeight: 1.4 }}>
            {t('brand_overlay_opacity_hint')}
          </span>
        </Field>
      </div>

      <div style={{ marginTop: 14 }}>
        <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 2 }}>{t('cover_lib')}</div>
        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, lineHeight: 1.5 }}>{t('cover_lib_multi_hint')}</div>
        <button className="btn" style={{ padding: '6px 11px', marginBottom: 8 }}
          onClick={() => studio.refs.filler.current?.click()}>
          <Icon name="upload" size={13} /> {t('rep_photos_upload')}
        </button>
        <input ref={studio.refs.filler} type="file" accept="image/*" multiple style={{ display: 'none' }}
          onChange={(e) => { studio.onFillerUpload(e.target.files); e.target.value = '' }} />
        <CoverPhotoPicker terms={terms} max={12}
          selected={(b.filler_images_base64 as string[]) ?? []}
          onChange={(urls) => set('filler_images_base64', urls as never)} />
      </div>

      {!compact && (
        <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.5 }}>{t('rep_images_hint')}</div>
      )}
    </div>
  )
}
