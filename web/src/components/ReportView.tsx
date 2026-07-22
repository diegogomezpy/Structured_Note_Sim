import { useI18n } from '../i18n/I18nProvider'
import Tabs from './Tabs'
import ReportPanel from './ReportPanel'
import PdfDesigner from './PdfDesigner'
import BatchReportPanel from './BatchReportPanel'
import { useBrandingStudio } from '../lib/useBrandingStudio'
import type { ConfigMeta, NoteTerms } from '../api/types'
import type { RunOpts } from './SetupRail'

/* The Report area, split into sub-tabs: Build (pick sections + generate the
   single-note PDF), Designer (the bespoke branding studio), and Batch (multi-
   config report making). The branding config is owned here so the Build tab
   (which sends it) and the Designer tab (which edits it) share one source. The
   rail's NavMenu drives `sub`; a Tabs row is the phone fallback. */
export default function ReportView({ terms, opts, variantB, pathImages, configs, sub, onSubChange }: {
  terms: NoteTerms
  opts: RunOpts
  variantB?: NoteTerms | null
  pathImages?: { title: string; png: string }[]
  configs: ConfigMeta[]
  sub: string
  onSubChange: (s: string) => void
}) {
  const { t } = useI18n()
  const studio = useBrandingStudio()
  const subTabs = [
    { id: 'build', label: t('rep_sub_build') },
    { id: 'design', label: t('rep_sub_design') },
    { id: 'batch', label: t('rep_sub_batch') },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div className="nav-mobile-only" style={{ marginTop: 2 }}>
        <Tabs tabs={subTabs} active={sub} onChange={onSubChange} />
      </div>

      {sub === 'design' ? (
        <PdfDesigner studio={studio} terms={terms} />
      ) : sub === 'batch' ? (
        <BatchReportPanel terms={terms} opts={opts} configs={configs} />
      ) : (
        <ReportPanel terms={terms} opts={opts} variantB={variantB} pathImages={pathImages}
                     brand={studio.brand} studio={studio} onOpenDesigner={() => onSubChange('design')} />
      )}
    </div>
  )
}
