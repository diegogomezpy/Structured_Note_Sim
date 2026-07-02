/* Note-type presets. Selecting a type stores an explicit `note_type` on the note
   (which drives the dedicated menu, the payoff branch, the diagram and the prose)
   and forces the fields that structure hard-codes. */
import type { NoteTerms } from '../api/types'

export type NoteType = 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'participation' | 'custom'

export const NOTE_TYPES: NoteType[] = ['phoenix', 'reverse_conv', 'growth_autocall', 'participation', 'custom']

/** The note's structure type. Prefer the explicit stored `note_type`; fall back to
    inferring it from the fields for older configs that predate the field. */
export function detectNoteType(t: NoteTerms): NoteType {
  if (t.note_type && NOTE_TYPES.includes(t.note_type)) return t.note_type
  if ((t.capital_guarantee ?? 0) > 0) return 'participation'
  if (t.coupon_at_autocall_only || (t.autocall_step_down ?? 0) > 0) return 'growth_autocall'
  if (t.coupon_barrier === 0 && !t.memory) return 'reverse_conv'
  return 'phoenix'
}

/** Return terms with the chosen structure's canonical fields forced; underlyings,
    maturity and any of that type's own parameters are preserved. */
export function applyPreset(t: NoteTerms, type: NoteType): NoteTerms {
  const n: NoteTerms = { ...t, note_type: type }
  switch (type) {
    case 'participation':
      // Maturity-only payoff — neutralise the entire Phoenix waterfall.
      n.coupon_pa = 0; n.coupon_barrier = 0; n.memory = false; n.knock_in_barrier = 0
      n.autocall_barrier = 2.0; n.autocall_step_down = null; n.autocall_floor = null
      n.coupon_at_autocall_only = false; n.one_star_level = null; n.capital_guarantee = 0
      n.participation_downside = n.participation_downside ?? 'full'
      n.participation_upside = n.participation_upside ?? 'linear'
      n.participation_basket = n.participation_basket ?? n.coupon_basket ?? 'worst_of'
      n.protection_level = n.protection_level ?? 1.0
      n.participation_rate = n.participation_rate ?? 1.0
      n.participation_strike = n.participation_strike ?? 1.0
      break
    case 'reverse_conv':
      n.coupon_barrier = 0; n.memory = false
      n.autocall_step_down = null; n.autocall_floor = null; n.coupon_at_autocall_only = false
      n.capital_guarantee = 0; n.upside_cap = null; n.one_star_level = null
      break
    case 'growth_autocall':
      n.memory = false; n.coupon_at_autocall_only = true
      n.capital_guarantee = 0; n.upside_cap = null; n.one_star_level = null
      break
    case 'phoenix':
      n.autocall_step_down = null; n.autocall_floor = null; n.coupon_at_autocall_only = false
      n.capital_guarantee = 0; n.upside_cap = null
      break
    case 'custom':
      break // leave everything as-is
  }
  return n
}
