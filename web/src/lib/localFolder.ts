import { useEffect, useState } from 'react'

/* Let the user point the app at their OWN local folder of note-config (or
   branding) JSONs, rather than only the examples bundled in the repo.

   The deployed site is a static front-end on Cloud Run — it cannot read a path
   on the user's machine. So we use the browser File System Access API: the user
   grants read access to a directory once, we scan it for *.json, and we persist
   the directory *handle* in IndexedDB so a return visit can re-scan with a single
   "reconnect" click (the browser re-prompts for permission each session — that is
   a security constraint, not something we can bypass). Browsers without the API
   (Safari/Firefox) fall back to a one-shot <input webkitdirectory> import. */

export const fsSupported =
  typeof window !== 'undefined' && 'showDirectoryPicker' in window

export interface LocalFile { name: string; raw: unknown }

// ── tiny IndexedDB key→value store for the persisted directory handles ───────
const DB = 'mercator-fs', STORE = 'handles'
function idb(): Promise<IDBDatabase> {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB, 1)
    r.onupgradeneeded = () => r.result.createObjectStore(STORE)
    r.onsuccess = () => res(r.result)
    r.onerror = () => rej(r.error)
  })
}
async function idbGet<T>(k: string): Promise<T | undefined> {
  const db = await idb()
  return new Promise((res, rej) => {
    const t = db.transaction(STORE).objectStore(STORE).get(k)
    t.onsuccess = () => res(t.result as T); t.onerror = () => rej(t.error)
  })
}
async function idbSet(k: string, v: unknown): Promise<void> {
  const db = await idb()
  return new Promise((res, rej) => {
    const tx = db.transaction(STORE, 'readwrite'); tx.objectStore(STORE).put(v, k)
    tx.oncomplete = () => res(); tx.onerror = () => rej(tx.error)
  })
}
async function idbDel(k: string): Promise<void> {
  const db = await idb()
  return new Promise((res, rej) => {
    const tx = db.transaction(STORE, 'readwrite'); tx.objectStore(STORE).delete(k)
    tx.oncomplete = () => res(); tx.onerror = () => rej(tx.error)
  })
}

/* eslint-disable @typescript-eslint/no-explicit-any */
async function scan(dir: any): Promise<LocalFile[]> {
  const out: LocalFile[] = []
  for await (const [name, h] of dir.entries()) {
    if (h.kind === 'file' && name.toLowerCase().endsWith('.json')) {
      try {
        const text = await (await h.getFile()).text()
        out.push({ name: name.replace(/\.json$/i, ''), raw: JSON.parse(text) })
      } catch { /* skip unreadable / non-JSON files */ }
    }
  }
  return out.sort((a, b) => a.name.localeCompare(b.name))
}

async function pickFolder(key: string): Promise<{ name: string; files: LocalFile[] }> {
  const dir = await (window as any).showDirectoryPicker({ id: key, mode: 'read' })
  await idbSet(key, dir).catch(() => {})
  return { name: dir.name, files: await scan(dir) }
}
async function restoreFolder(key: string): Promise<{ name: string; files: LocalFile[]; needsGrant: boolean } | null> {
  const dir = await idbGet<any>(key).catch(() => undefined)
  if (!dir) return null
  const perm = await dir.queryPermission({ mode: 'read' })
  if (perm === 'granted') return { name: dir.name, files: await scan(dir), needsGrant: false }
  return { name: dir.name, files: [], needsGrant: true }
}
async function reconnectFolder(key: string): Promise<{ name: string; files: LocalFile[] } | null> {
  const dir = await idbGet<any>(key).catch(() => undefined)
  if (!dir) return null
  if (await dir.requestPermission({ mode: 'read' }) !== 'granted') return null
  return { name: dir.name, files: await scan(dir) }
}

// Filesystem-illegal characters only — spaces, dashes and accents are kept so an
// edit saves back over the very file it was loaded from.
const safeName = (s: string) => (s || 'note').replace(/[/\\:*?"<>|]/g, '_').slice(0, 80).trim() || 'note'

/** Write `obj` as pretty JSON into the connected folder, overwriting `<name>.json`
    (the existing file when editing one loaded from the folder, else a new file).
    Upgrades the directory handle to read-write — the browser prompts once per
    session. Returns the saved base name (no extension), or throws if denied. */
async function writeFile(key: string, name: string, obj: unknown): Promise<string> {
  const dir = await idbGet<any>(key).catch(() => undefined)
  if (!dir) throw new Error('no folder connected')
  let perm = await dir.queryPermission({ mode: 'readwrite' })
  if (perm !== 'granted') perm = await dir.requestPermission({ mode: 'readwrite' })
  if (perm !== 'granted') throw new Error('write permission denied')
  const base = safeName(name)
  const fh = await dir.getFileHandle(`${base}.json`, { create: true })
  const w = await fh.createWritable()
  await w.write(JSON.stringify(obj, null, 2))
  await w.close()
  return base
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ── image-folder variant (for the report photo pool) ─────────────────────────
export interface ImageFile { name: string; dataUrl: string }
const IMG_RE = /\.(png|jpe?g|webp|avif|gif|bmp)$/i

function blobToDataURL(b: Blob): Promise<string> {
  return new Promise((res, rej) => {
    const r = new FileReader(); r.onload = () => res(String(r.result)); r.onerror = rej; r.readAsDataURL(b)
  })
}
/* eslint-disable @typescript-eslint/no-explicit-any */
async function scanImages(dir: any): Promise<ImageFile[]> {
  const out: ImageFile[] = []
  for await (const [name, h] of dir.entries()) {
    if (h.kind === 'file' && IMG_RE.test(name)) {
      try { out.push({ name: name.replace(IMG_RE, ''), dataUrl: await blobToDataURL(await h.getFile()) }) }
      catch { /* skip unreadable */ }
    }
  }
  return out.sort((a, b) => a.name.localeCompare(b.name))
}
async function pickImages(key: string) {
  const dir = await (window as any).showDirectoryPicker({ id: key, mode: 'read' })
  await idbSet(key, dir).catch(() => {})
  return { name: dir.name as string, files: await scanImages(dir) }
}
async function restoreImages(key: string) {
  const dir = await idbGet<any>(key).catch(() => undefined)
  if (!dir) return null
  const perm = await dir.queryPermission({ mode: 'read' })
  if (perm === 'granted') return { name: dir.name as string, files: await scanImages(dir), needsGrant: false }
  return { name: dir.name as string, files: [] as ImageFile[], needsGrant: true }
}
async function reconnectImages(key: string) {
  const dir = await idbGet<any>(key).catch(() => undefined)
  if (!dir) return null
  if (await dir.requestPermission({ mode: 'read' }) !== 'granted') return null
  return { name: dir.name as string, files: await scanImages(dir) }
}
/* eslint-enable @typescript-eslint/no-explicit-any */

/** React state for a connected local folder of IMAGES — auto-detected and offered
    as report photos. Read-only (no save); otherwise mirrors `useLocalFolder`. */
export function useLocalImages(key: string) {
  const [files, setFiles] = useState<ImageFile[]>([])
  const [folder, setFolder] = useState<string | null>(null)
  const [needsGrant, setNeedsGrant] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!fsSupported) return
    restoreImages(key)
      .then((r) => { if (r) { setFolder(r.name); setFiles(r.files); setNeedsGrant(r.needsGrant) } })
      .catch(() => {})
  }, [key])

  const connect = async () => {
    setBusy(true)
    try { const r = await pickImages(key); setFolder(r.name); setFiles(r.files); setNeedsGrant(false) }
    catch { /* cancelled */ } finally { setBusy(false) }
  }
  const reconnect = async () => {
    setBusy(true)
    try { const r = await reconnectImages(key); if (r) { setFolder(r.name); setFiles(r.files); setNeedsGrant(false) } }
    catch { /* denied */ } finally { setBusy(false) }
  }
  const refresh = async () => {
    if (needsGrant) return reconnect()
    setBusy(true)
    try { const r = await restoreImages(key); if (r) { setFiles(r.files); setNeedsGrant(r.needsGrant) } }
    catch { /* gone */ } finally { setBusy(false) }
  }
  const disconnect = async () => {
    await idbDel(key).catch(() => {})
    setFolder(null); setFiles([]); setNeedsGrant(false)
  }
  // Browsers without the FS Access API: one-shot <input webkitdirectory> import.
  const importFiles = async (list: FileList | null) => {
    if (!list?.length) return
    const out: ImageFile[] = []
    for (const f of Array.from(list)) {
      if (!IMG_RE.test(f.name)) continue
      try { out.push({ name: f.name.replace(IMG_RE, ''), dataUrl: await blobToDataURL(f) }) } catch { /* skip */ }
    }
    if (out.length) { setFiles(out.sort((a, b) => a.name.localeCompare(b.name))); setFolder('imported') }
  }

  return { supported: fsSupported, files, folder, needsGrant, busy, connect, reconnect, refresh, disconnect, importFiles }
}

/** React state for a connected local folder of JSONs (configs or branding).
    `key` namespaces the persisted handle so configs and branding stay separate. */
export function useLocalFolder(key: string) {
  const [files, setFiles] = useState<LocalFile[]>([])
  const [folder, setFolder] = useState<string | null>(null)
  const [needsGrant, setNeedsGrant] = useState(false)
  const [busy, setBusy] = useState(false)

  // On load, recover a previously-connected folder (read-only until reconnected).
  useEffect(() => {
    if (!fsSupported) return
    restoreFolder(key)
      .then((r) => { if (r) { setFolder(r.name); setFiles(r.files); setNeedsGrant(r.needsGrant) } })
      .catch(() => {})
  }, [key])

  const connect = async () => {
    setBusy(true)
    try { const r = await pickFolder(key); setFolder(r.name); setFiles(r.files); setNeedsGrant(false) }
    catch { /* user cancelled */ }
    finally { setBusy(false) }
  }
  const reconnect = async () => {
    setBusy(true)
    try { const r = await reconnectFolder(key); if (r) { setFolder(r.name); setFiles(r.files); setNeedsGrant(false) } }
    catch { /* denied */ }
    finally { setBusy(false) }
  }
  const refresh = async () => {
    if (needsGrant) return reconnect()
    setBusy(true)
    try { const r = await restoreFolder(key); if (r) { setFiles(r.files); setNeedsGrant(r.needsGrant) } }
    catch { /* gone */ }
    finally { setBusy(false) }
  }
  const disconnect = async () => {
    await idbDel(key).catch(() => {})
    setFolder(null); setFiles([]); setNeedsGrant(false)
  }
  // Write the current config back into the folder (overwriting `<name>.json`),
  // then re-scan so the list reflects it. Throws if the user denies write access.
  const save = async (name: string, obj: unknown): Promise<string> => {
    setBusy(true)
    try {
      const saved = await writeFile(key, name, obj)
      const r = await restoreFolder(key)
      if (r) { setFiles(r.files); setNeedsGrant(r.needsGrant) }
      return saved
    } finally { setBusy(false) }
  }
  // Fallback for browsers without the File System Access API: a one-shot import
  // of every JSON in a chosen folder (no persistence — re-pick each session).
  const importFiles = async (list: FileList | null) => {
    if (!list?.length) return
    const out: LocalFile[] = []
    for (const f of Array.from(list)) {
      if (!f.name.toLowerCase().endsWith('.json')) continue
      try { out.push({ name: f.name.replace(/\.json$/i, ''), raw: JSON.parse(await f.text()) }) } catch { /* skip */ }
    }
    if (out.length) { setFiles(out.sort((a, b) => a.name.localeCompare(b.name))); setFolder('imported') }
  }

  // Writes need the File System Access API + a real connected directory handle
  // (the webkitdirectory import fallback has no handle, so it can't save back).
  const canSave = fsSupported && !!folder && folder !== 'imported'

  return { supported: fsSupported, files, folder, needsGrant, busy, canSave, connect, reconnect, refresh, disconnect, importFiles, save }
}
