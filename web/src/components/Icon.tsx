type Name = 'sun' | 'moon' | 'play' | 'refresh' | 'chart' | 'spinner' | 'x' | 'plus' | 'info' | 'check' | 'upload' | 'download' | 'save'

const PATHS: Record<Name, string> = {
  sun: 'M12 4V2M12 22v-2M4 12H2m20 0h-2M6.3 6.3 4.9 4.9m14.2 14.2-1.4-1.4M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z',
  play: 'M6 4l14 8-14 8V4Z',
  refresh: 'M3 12a9 9 0 0 1 15.5-6.2M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.2M3 21v-5h5',
  chart: 'M4 19V5m0 14h16M8 16V9m4 7V6m4 10v-4',
  spinner: 'M12 3a9 9 0 1 0 9 9',
  x: 'M18 6 6 18M6 6l12 12',
  plus: 'M12 5v14M5 12h14',
  info: 'M12 16v-4m0-4h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z',
  check: 'M20 6 9 17l-5-5',
  upload: 'M12 16V4m0 0L7 9m5-5 5 5M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2',
  download: 'M12 4v12m0 0 5-5m-5 5-5-5M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2',
  // floppy-disk save
  save: 'M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2ZM17 21v-8H7v8M7 3v5h8',
}

export default function Icon({ name, size = 16 }: { name: Name; size?: number }) {
  const fill = name === 'play' ? 'currentColor' : 'none'
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill={fill}
      stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round"
      className={name === 'spinner' ? 'spin' : undefined}
      style={name === 'spinner' ? { animation: 'spin 0.8s linear infinite' } : undefined}
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
