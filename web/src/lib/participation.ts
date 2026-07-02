/* Participation Note maturity redemption — the TS mirror of
   core/note.py:_participation_redemption. Used by the payoff-profile diagram so
   the picture always matches what the engine prices. Keep the two in sync. */
import type { NoteTerms } from '../api/types'

const clamp = (x: number, lo: number, hi: number) => Math.min(Math.max(x, lo), hi)

/** Redemption (fraction of notional) for a final basket level `B`. */
export function participationRedemption(B: number, t: NoteTerms): number {
  const strike = t.participation_strike ?? 1
  const rate = t.participation_rate ?? 1
  const prot = t.protection_level ?? 0
  const cap = t.upside_cap != null ? 1 + t.upside_cap : Infinity
  const pu = t.participation_upside ?? 'linear'
  const pd = t.participation_downside ?? 'full'

  if (pd === 'bear') return clamp(1 + rate * Math.max(0, strike - B), prot, cap)

  let up: number
  if (pu === 'digital') up = t.digital_payout ?? 0
  else if (pu === 'shark_fin') up = (t.knockout_level != null && B >= t.knockout_level) ? (t.knockout_rebate ?? 0) : rate * (B - strike)
  else up = rate * (B - strike)
  const Rup = Math.min(1 + up, cap)

  let Rdn: number
  if (pd === 'buffer') Rdn = B >= prot ? 1 : 1 - (prot - B)
  else if (pd === 'airbag') Rdn = B >= prot ? 1 : (prot > 0 ? B / prot : 0)
  else Rdn = Math.min(prot, 1)

  return Math.max(B >= strike ? Rup : Rdn, 0)
}
