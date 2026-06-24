/** Custom mark: a worst-of path stepping down toward a dashed knock-in barrier,
    then an autocall node — an ownable glyph for the product, not a stock icon.
    Uses currentColor so the parent tile controls the color. */
export default function BrandMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 16h18" strokeDasharray="2.2 2.4" opacity={0.65} />
      <path d="M3 8.5 L8 12.5 L12.5 6.5 L18 5" />
      <circle cx="18" cy="5" r="2.1" fill="currentColor" stroke="none" />
    </svg>
  )
}
