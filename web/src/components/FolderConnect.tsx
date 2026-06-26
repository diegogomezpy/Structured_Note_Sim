import { useRef } from 'react'
import Icon from './Icon'
import { useI18n } from '../i18n/I18nProvider'
import type { useLocalFolder } from '../lib/localFolder'

/** Compact controls for a connected local folder (configs or branding). The
    parent owns the useLocalFolder state (so it can merge the scanned files into
    its selector); this just renders connect / reconnect / refresh / disconnect.
    Browsers without the File System Access API get a one-shot folder import. */
export default function FolderConnect({ fld }: { fld: ReturnType<typeof useLocalFolder> }) {
  const { t } = useI18n()
  const importRef = useRef<HTMLInputElement>(null)
  const { supported, folder, needsGrant, busy, files, connect, refresh, disconnect, importFiles } = fld

  const btn: React.CSSProperties = { padding: '3px 9px', fontSize: 11.5 }

  // Fallback (Safari/Firefox): a one-shot <input webkitdirectory> import.
  if (!supported) {
    return (
      <div style={{ marginTop: 8 }}>
        <button className="btn btn--ghost" style={btn} onClick={() => importRef.current?.click()}>
          <Icon name="upload" size={13} /> {folder ? t('folder_reimport', { n: files.length }) : t('folder_import')}
        </button>
        <input ref={importRef} type="file" multiple style={{ display: 'none' }}
               {...{ webkitdirectory: '' } as Record<string, string>}
               onChange={(e) => { importFiles(e.target.files); e.target.value = '' }} />
      </div>
    )
  }

  if (!folder) {
    return (
      <button className="btn btn--ghost" style={{ ...btn, marginTop: 8 }} onClick={connect} disabled={busy}>
        <Icon name={busy ? 'spinner' : 'plus'} size={13} /> {t('folder_connect')}
      </button>
    )
  }

  if (needsGrant) {
    return (
      <button className="btn" style={{ ...btn, marginTop: 8, color: 'var(--amber)', borderColor: 'var(--amber)' }} onClick={refresh} disabled={busy}>
        <Icon name={busy ? 'spinner' : 'refresh'} size={13} /> {t('folder_reconnect', { name: folder })}
      </button>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, fontSize: 11.5, color: 'var(--text-muted)', flexWrap: 'wrap' }}>
      <span className="tag tag--accent" style={{ gap: 5 }}>
        <Icon name="check" size={12} /> {folder} · {t('folder_count', { n: files.length })}
      </span>
      <button className="btn btn--ghost" style={btn} onClick={refresh} disabled={busy} title={t('folder_refresh')}>
        <Icon name={busy ? 'spinner' : 'refresh'} size={12} />
      </button>
      <button className="btn btn--ghost" style={btn} onClick={disconnect} title={t('folder_disconnect')}>
        <Icon name="x" size={12} />
      </button>
    </div>
  )
}
