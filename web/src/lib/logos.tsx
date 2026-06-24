import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { LogoData } from '../api/types'

/** Resolves logo URLs. `ticker(sym)` → curated map (parqet for stocks, Google
    favicons for indices) with a parqet-by-symbol fallback for anything else.
    `issuer(name)` → bank favicon. Both return '' until the data has loaded. */
interface LogoApi {
  ticker: (sym: string) => string
  issuer: (name: string) => string
}

const Ctx = createContext<LogoApi>({ ticker: () => '', issuer: () => '' })

export function LogoProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<LogoData | null>(null)
  useEffect(() => { api.logos().then(setData).catch(() => {}) }, [])

  const value = useMemo<LogoApi>(() => ({
    ticker: (sym) => {
      if (!data || !sym) return ''
      return data.map[sym] ?? data.base.replace('{sym}', encodeURIComponent(sym))
    },
    issuer: (name) => {
      if (!data || !name) return ''
      return data.issuers[name] ?? data.issuers[name.trim()] ?? ''
    },
  }), [data])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useLogos = () => useContext(Ctx)
