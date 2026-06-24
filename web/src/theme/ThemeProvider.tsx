import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Mode = 'light' | 'dark'

interface ThemeCtx {
  mode: Mode
  toggle: () => void
}

const Ctx = createContext<ThemeCtx>({ mode: 'light', toggle: () => {} })

function initialMode(): Mode {
  const saved = localStorage.getItem('sns-theme')
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(initialMode)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode)
    localStorage.setItem('sns-theme', mode)
  }, [mode])

  const toggle = () => setMode((m) => (m === 'light' ? 'dark' : 'light'))
  return <Ctx.Provider value={{ mode, toggle }}>{children}</Ctx.Provider>
}

export const useTheme = () => useContext(Ctx)
