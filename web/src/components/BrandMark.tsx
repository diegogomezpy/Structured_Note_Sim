/** Mercator mark — a meridian: globe circle, meridian arc, and the zenith
 *  node (the autocall / observation apex). Uses currentColor so the parent
 *  tile controls the color (matches the previous BrandMark API).
 *
 *  Usage (unchanged from before):
 *    <div style={{ background: 'var(--accent)', color: '#fffefb' }}>
 *      <BrandMark size={22} />
 *    </div>
 */
export default function BrandMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="16" cy="16" r="12" />
      <ellipse cx="16" cy="16" rx="5" ry="12" />
      <line x1="4" y1="16" x2="28" y2="16" opacity={0.4} />
      <circle cx="16" cy="4" r="1.9" fill="currentColor" stroke="none" />
    </svg>
  )
}
