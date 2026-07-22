import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nProvider'
import { useToast } from '../components/Toast'
import { useLocalFolder } from './localFolder'
import type { Branding } from '../api/types'

/* Single source of truth for the PDF branding config + all its editing helpers.
   Owned once (in ReportView) and shared by the Build tab (which sends `brand` in
   the report request) and the PDF Designer tab (which edits it). Keeps the
   branding logic out of the individual panels. */

export const COVER_METRIC_KEYS = [
  'maturity', 'coupon_pa', 'coupon_barrier', 'autocall_barrier',
  'knock_in_barrier', 'issue_date', 'issuer',
] as const
export const COVER_METRIC_DEFAULT = ['coupon_pa', 'maturity', 'knock_in_barrier']
export const COVER_METRIC_MAX = 4
const MAX_PHOTOS = 12

// Fonts the PDF can actually render, discovered by the API from fonts/ and
// fonts/brand/. Dropping a <Name>-<Style>.ttf into fonts/brand/ adds it here
// automatically — and the preview loads the very same file, so what you pick is
// what the report renders.
export interface ReportFont { family: string; file: string; styles: string[]; builtin: boolean }

export interface BrandingStudio {
  brand: Branding
  setBrand: React.Dispatch<React.SetStateAction<Branding>>
  setBrandField: <K extends keyof Branding>(k: K, v: Branding[K]) => void
  themeIsCustom: boolean
  presets: { file: string; firm_name: string }[]
  reportFonts: ReportFont[]
  brandFolder: ReturnType<typeof useLocalFolder>
  brandLocalName: string | null
  setBrandLocalName: (n: string | null) => void
  brandSaving: boolean
  error: string
  setError: (s: string) => void
  applyBranding: (b: Record<string, unknown>) => void
  newBranding: () => void
  loadPreset: (file: string) => Promise<void>
  onUploadBranding: (file: File | undefined) => void
  saveBrandingToFolder: () => Promise<void>
  downloadBranding: () => void
  onImage: (field: keyof Branding, file: File | undefined) => void
  onFillerUpload: (files: FileList | null) => void
  onFontFiles: (field: 'title_font_files' | 'body_font_files', files: FileList | null) => void
  fontCount: (field: 'title_font_files' | 'body_font_files') => number
  coverMetricsSel: string[]
  toggleCoverMetric: (k: string) => void
  metricLabel: (k: string) => string
  refs: {
    logo: React.RefObject<HTMLInputElement | null>
    altLogo: React.RefObject<HTMLInputElement | null>
    sigil: React.RefObject<HTMLInputElement | null>
    filler: React.RefObject<HTMLInputElement | null>
    cfg: React.RefObject<HTMLInputElement | null>
    titleFont: React.RefObject<HTMLInputElement | null>
    bodyFont: React.RefObject<HTMLInputElement | null>
  }
}

export function useBrandingStudio(): BrandingStudio {
  const { t, lang } = useI18n()
  const toast = useToast()
  const [brand, setBrand] = useState<Branding>({})
  const [presets, setPresets] = useState<{ file: string; firm_name: string }[]>([])
  const [reportFonts, setReportFonts] = useState<ReportFont[]>([])
  const brandFolder = useLocalFolder('branding')
  const [brandLocalName, setBrandLocalName] = useState<string | null>(null)
  const [brandSaving, setBrandSaving] = useState(false)
  const [error, setError] = useState('')

  const refs = {
    logo: useRef<HTMLInputElement>(null),
    altLogo: useRef<HTMLInputElement>(null),
    sigil: useRef<HTMLInputElement>(null),
    filler: useRef<HTMLInputElement>(null),
    cfg: useRef<HTMLInputElement>(null),
    titleFont: useRef<HTMLInputElement>(null),
    bodyFont: useRef<HTMLInputElement>(null),
  }

  useEffect(() => { api.brandingList().then(setPresets).catch(() => {}) }, [])
  useEffect(() => { api.fonts().then(setReportFonts).catch(() => {}) }, [])

  const setBrandField = <K extends keyof Branding>(k: K, v: Branding[K]) => setBrand((b) => {
    const empty = v === '' || v == null || (Array.isArray(v) && v.length === 0)
    return { ...b, [k]: empty ? undefined : v }
  })
  const themeIsCustom = !!brand.report_theme && typeof brand.report_theme === 'object'

  const applyBranding = (b: Record<string, unknown>) => {
    const flat = (v: unknown) => (v && typeof v === 'object' && !Array.isArray(v) ? ((v as Record<string, string>)[lang] ?? (v as Record<string, string>).en ?? '') : v)
    setBrand({
      ...b,
      report_title: flat(b.report_title),
      footer_note: flat(b.footer_note),
      disclaimer_body: flat(b.disclaimer_body),
    } as Branding)
  }
  const newBranding = () => {
    setBrandLocalName(null)
    setBrand({})
    setError('')
  }
  const loadPreset = async (file: string) => {
    if (!file) return
    setBrandLocalName(null)
    try { applyBranding(await api.branding(file) as Record<string, unknown>) } catch { /* ignore */ }
  }
  const onUploadBranding = (file: File | undefined) => {
    if (!file) return
    setBrandLocalName(null)
    const r = new FileReader()
    r.onload = () => {
      try { applyBranding(JSON.parse(String(r.result))); setError('') }
      catch { setError(t('brand_upload_bad')) }
    }
    r.readAsText(file)
  }
  const saveBrandingToFolder = async () => {
    setBrandSaving(true)
    try {
      const saved = await brandFolder.save(brandLocalName ?? (brand.firm_name || 'branding'), brand)
      setBrandLocalName(saved)
      toast.push({ title: t('brand_saved'), sub: `${saved}.json · ${brandFolder.folder}`, tone: 'accent', icon: 'check' })
    } catch {
      toast.push({ title: t('cfg_save_failed'), sub: t('cfg_save_failed_sub'), tone: 'red', icon: 'info' })
    } finally { setBrandSaving(false) }
  }
  const downloadBranding = () => {
    const json = JSON.stringify(brand, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const fname = `${(brandLocalName || brand.firm_name || 'branding').replace(/[^A-Za-z0-9]+/g, '_').toLowerCase()}_branding.json`
    const a = document.createElement('a')
    a.href = url; a.download = fname
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
    toast.push({ title: t('brand_downloaded'), sub: fname, tone: 'accent' })
  }
  const onImage = (field: keyof Branding, file: File | undefined) => {
    if (!file) return
    const r = new FileReader(); r.onload = () => setBrandField(field, String(r.result) as Branding[keyof Branding]); r.readAsDataURL(file)
  }
  const onFillerUpload = (files: FileList | null) => {
    if (!files || !files.length) return
    Promise.all(Array.from(files).map((f) => new Promise<string>((res, rej) => {
      const r = new FileReader(); r.onload = () => res(String(r.result)); r.onerror = rej; r.readAsDataURL(f)
    }))).then((urls) => setBrand((b) => {
      const cur = (b.filler_images_base64 as string[] | undefined) ?? []
      const room = Math.max(0, MAX_PHOTOS - cur.length)
      return { ...b, filler_images_base64: [...cur, ...urls.slice(0, room)] }
    })).catch(() => {})
  }
  const styleOf = (name: string) => {
    const n = name.toLowerCase().replace(/[^a-z]/g, '')
    if (n.includes('bold') && n.includes('italic')) return 'BoldItalic'
    if (n.includes('italic')) return 'Italic'
    if (n.includes('bold')) return 'Bold'
    return 'Regular'
  }
  const onFontFiles = (field: 'title_font_files' | 'body_font_files', files: FileList | null) => {
    if (!files || !files.length) return
    const acc: Record<string, string> = { ...((brand[field] as Record<string, string>) ?? {}) }
    let pending = files.length
    Array.from(files).forEach((f) => {
      const r = new FileReader()
      r.onload = () => {
        const s = String(r.result)
        acc[styleOf(f.name)] = s.includes(',') ? s.split(',')[1] : s
        if (--pending === 0) setBrand((b) => ({ ...b, [field]: acc }))
      }
      r.readAsDataURL(f)
    })
  }
  const fontCount = (field: 'title_font_files' | 'body_font_files') =>
    Object.keys((brand[field] as Record<string, string>) ?? {}).length

  const metricLabel = (k: string) => k === 'issuer' ? t('issuer_name') : t(k)
  const coverMetricsSel = (brand.cover_metrics as string[] | undefined) ?? COVER_METRIC_DEFAULT
  const toggleCoverMetric = (k: string) => {
    const base = (brand.cover_metrics as string[] | undefined) ?? COVER_METRIC_DEFAULT
    const next = base.includes(k) ? base.filter((m) => m !== k) : [...COVER_METRIC_KEYS].filter((m) => base.includes(m) || m === k)
    setBrand((b) => ({ ...b, cover_metrics: next }))
  }

  return {
    brand, setBrand, setBrandField, themeIsCustom, presets, reportFonts, brandFolder,
    brandLocalName, setBrandLocalName, brandSaving, error, setError,
    applyBranding, newBranding, loadPreset, onUploadBranding, saveBrandingToFolder, downloadBranding,
    onImage, onFillerUpload, onFontFiles, fontCount,
    coverMetricsSel, toggleCoverMetric, metricLabel, refs,
  }
}
