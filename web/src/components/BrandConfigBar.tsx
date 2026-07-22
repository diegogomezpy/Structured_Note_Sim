import { useI18n } from '../i18n/I18nProvider'
import Icon from './Icon'
import FolderConnect from './FolderConnect'
import { inputStyle } from './designerFields'
import type { BrandingStudio } from '../lib/useBrandingStudio'

/* Branding-config management: start a new one, load a saved one (from the
   connected folder or a server preset), name it, upload/download JSON, save.
   Rendered in the PDF Designer in full, and in `compact` form on the Build tab
   — you often just want to swap the brand config for this report without
   detouring into the Designer. Both edit the same shared studio state. */
export default function BrandConfigBar({ studio, compact }: { studio: BrandingStudio; compact?: boolean }) {
  const { t } = useI18n()

  const loadSelect = (
    <select value="" onChange={(e) => {
      const v = e.target.value
      if (v === '__new') { studio.newBranding(); return }
      if (v.startsWith('local:')) {
        const f = studio.brandFolder.files.find((x) => `local:${x.name}` === v)
        if (f) { studio.setBrandLocalName(f.name); studio.applyBranding(f.raw as Record<string, unknown>) }
      } else if (v) studio.loadPreset(v)
    }} style={{ ...inputStyle, width: 'auto', minWidth: 180 }}>
      <option value="">{t('brand_preset_ph')}</option>
      {!compact && <option value="__new">{t('brand_new')}</option>}
      {studio.brandFolder.files.map((f) => (
        <option key={f.name} value={`local:${f.name}`}>{f.name} {t('folder_tag')}</option>
      ))}
      {studio.presets.map((p) => <option key={p.file} value={p.file}>{p.firm_name}</option>)}
    </select>
  )

  const uploadInput = (
    <input ref={studio.refs.cfg} type="file" accept="application/json,.json" style={{ display: 'none' }}
      onChange={(e) => { studio.onUploadBranding(e.target.files?.[0]); e.target.value = '' }} />
  )

  if (compact) {
    const active = studio.brandLocalName || studio.brand.firm_name
    return (
      <div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
          {loadSelect}
          <button className="btn" style={{ padding: '7px 12px' }} onClick={() => studio.refs.cfg.current?.click()}>
            <Icon name="upload" size={13} /> {t('brand_upload_cfg_btn')}
          </button>
          <FolderConnect fld={studio.brandFolder} />
          {active && (
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
              {t('rep_brand_active')} <strong style={{ color: 'var(--text)' }}>{active}</strong>
            </span>
          )}
          {uploadInput}
        </div>
        {studio.error && <div style={{ fontSize: 12, color: 'var(--red, #c0392b)', marginTop: 6 }}>{studio.error}</div>}
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
        <button className="btn btn--primary" style={{ padding: '7px 12px' }} onClick={studio.newBranding}
          title={t('brand_new_hint')}><Icon name="plus" size={13} /> {t('brand_new')}</button>
        {loadSelect}
        {/* config name — used as the saved filename */}
        <input type="text" value={studio.brandLocalName ?? ''} placeholder={t('brand_config_name')}
          onChange={(e) => studio.setBrandLocalName(e.target.value || null)}
          style={{ ...inputStyle, width: 'auto', minWidth: 150 }} />
        <FolderConnect fld={studio.brandFolder} />
        <div style={{ flex: 1 }} />
        <button className="btn" style={{ padding: '7px 12px' }} onClick={() => studio.refs.cfg.current?.click()}>
          <Icon name="upload" size={13} /> {t('brand_upload_cfg_btn')}
        </button>
        <button className="btn" style={{ padding: '7px 12px' }} onClick={studio.downloadBranding}>
          <Icon name="download" size={13} /> {t('brand_save_cfg_btn')}
        </button>
        {studio.brandFolder.canSave && (
          <button className="btn" style={{ padding: '7px 12px' }} disabled={studio.brandSaving} onClick={studio.saveBrandingToFolder}>
            <Icon name={studio.brandSaving ? 'spinner' : 'save'} size={13} /> {t('brand_save_to_folder_btn')}
          </button>
        )}
        {uploadInput}
      </div>
      {studio.error && <div style={{ fontSize: 12, color: 'var(--red, #c0392b)', marginTop: 6 }}>{studio.error}</div>}
    </div>
  )
}
