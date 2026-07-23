/* Participation Note maturity redemption — the TS mirror of
   core/note.py:_participation_redemption. Used by the payoff-profile diagram so
   the picture always matches what the engine prices. Keep the two in sync. */
import type { NoteTerms } from '../api/types'

/** Redemption (fraction of notional) for a final basket level `B`. */
export function participationRedemption(B: number, t: NoteTerms): number {
  const strike = t.participation_strike ?? 1
  const rate = t.participation_rate ?? 1
  const prot = t.protection_level ?? 0
  // upside_cap caps the UNDERLYING move that participates (min(B − strike, cap)),
  // not the redemption — participation is applied after the cap, so the ceiling
  // is 1 + rate·cap and the participating gain tops out at the same underlying
  // level whatever the rate. Matches core/note.py:_participation_redemption.
  const cap = t.upside_cap != null ? t.upside_cap : Infinity
  const pu = t.participation_upside ?? 'linear'
  const pd = t.participation_downside ?? 'full'

  if (pd === 'bear') return Math.max(prot, 1 + rate * Math.min(Math.max(0, strike - B), cap))

  const linR = 1 + rate * Math.min(B - strike, cap)
  let Rup: number
  if (pu === 'digital') Rup = 1 + (t.digital_payout ?? 0)
  else if (pu === 'shark_fin' && t.knockout_level != null) Rup = B >= t.knockout_level ? (t.knockout_payout ?? 1) : linR
  else Rup = linR

  let Rdn: number
  if (pd === 'buffer') Rdn = B >= prot ? 1 : 1 - (prot - B)
  else if (pd === 'airbag') Rdn = B >= prot ? 1 : (prot > 0 ? B / prot : 0)
  else Rdn = Math.min(prot, 1)

  return Math.max(B >= strike ? Rup : Rdn, 0)
}

/** Switch the downside style, seeding sensible defaults so the mode actually
    engages (a buffer/airbag at 100% protection would be a no-op). */
export function withDownside(t: NoteTerms, v: NonNullable<NoteTerms['participation_downside']>): NoteTerms {
  const n = { ...t, participation_downside: v }
  if ((v === 'buffer' || v === 'airbag') && (n.protection_level == null || n.protection_level >= 1))
    n.protection_level = v === 'airbag' ? 0.6 : 0.8
  return n
}

/** Switch the upside style, seeding the parameters that style needs (otherwise a
    shark-fin with no knock-out, or a digital with a 0 payout, renders as a flat
    line and looks broken). */
export function withUpside(t: NoteTerms, v: NonNullable<NoteTerms['participation_upside']>): NoteTerms {
  const n = { ...t, participation_upside: v }
  if (v === 'shark_fin' && n.knockout_level == null) { n.knockout_level = 1.3; if (n.knockout_payout == null) n.knockout_payout = 1.0 }
  if (v === 'digital' && !n.digital_payout) n.digital_payout = 0.1
  return n
}
