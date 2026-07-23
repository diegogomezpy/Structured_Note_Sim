import { useEffect } from 'react'
import { useI18n } from '../i18n/I18nProvider'
import Tabs from './Tabs'
import ReportPanel from './ReportPanel'
import BatchReportPanel from './BatchReportPanel'
import { useNavigate } from '../lib/useHashRoute'
import type { BrandingStudio } from '../lib/useBrandingStudio'
import type { ConfigMeta, NoteTerms } from '../api/types'
import type { RunOpts } from './SetupRail'

/* The Report area: Build (pick sections + generate the single-note PDF) and
   Batch (multi-config report making).

   Report *design* used to be a third sub-tab here, sharing the width with the
   note-setup rail. It now lives at #/studio as a page of its own; the old
   `design` sub id survives only as a redirect, so a rail selection or a
   remembered sub from a previous session still lands somewhere sensible.

   The branding studio itself is owned by App — it has to outlive this view, or
   switching to Monte Carlo and back would discard unsaved brand edits. */
export default function ReportView({ terms, opts, variantB, pathImages, configs, studio, sub, onSubChange }: {
  terms: NoteTerms
  opts: RunOpts
  variantB?: NoteTerms | null
  pathImages?: { title: string; png: string }[]
  configs: ConfigMeta[]
  studio: BrandingStudio
  sub: string
  onSubChange: (s: string) => void
}) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const subTabs = [
    { id: 'build', label: t('rep_sub_build') },
    { id: 'batch', label: t('rep_sub_batch') },
  ]

  // Legacy `design` sub → the Studio page. In an effect, not during render:
  // navigating sets the hash, and that must not happen mid-render.
  useEffect(() => {
    if (sub === 'design') { onSubChange('build'); navigate('/studio') }
  }, [sub, onSubChange, navigate])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }} className="fade-up">
      <div className="nav-mobile-only" style={{ marginTop: 2 }}>
        <Tabs tabs={subTabs} active={sub === 'batch' ? 'batch' : 'build'} onChange={onSubChange} />
      </div>

      {sub === 'batch' ? (
        <BatchReportPanel terms={terms} opts={opts} configs={configs} />
      ) : (
        <ReportPanel terms={terms} opts={opts} variantB={variantB} pathImages={pathImages}
                     brand={studio.brand} studio={studio} onOpenDesigner={() => navigate('/studio')} />
      )}
    </div>
  )
}
