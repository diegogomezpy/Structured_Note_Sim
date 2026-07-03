/* Note-type presets. Selecting a type stores an explicit `note_type` on the note
   (which drives the dedicated menu, the payoff branch, the diagram and the prose)
   and forces the fields that structure hard-codes.

   PARKED (temporarily removed from the pickable NOTE_TYPES until each is redesigned
   with its own good payoff + menus — reintroduce one at a time):
     - reverse_conv    — reverse convertible: guaranteed coupon (no coupon barrier),
                         no memory. Rides the Phoenix waterfall (coupon_barrier=0).
     - growth_autocall — no periodic coupon; premium accrues and pays as a lump at
                         autocall (coupon_at_autocall_only), often with a step-down
                         autocall barrier.
     - custom          — leave every field exactly as-is (no preset forcing).
   The NoteType union + applyPreset cases below are kept intact so old configs of
   these types still load and price via the Phoenix waterfall; they're just not
   offered in the UI. See CLAUDE.md "Note types". */
import type { NoteTerms } from '../api/types'

export type NoteType = 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'participation' | 'custom'

/** The user-pickable structure types. Trimmed to the two with dedicated, trusted
    behaviour; the parked ones (see header) will be reintroduced as they're nailed down. */
export const NOTE_TYPES: NoteType[] = ['phoenix', 'participation']

/** The note's structure type for the UI. Only Phoenix and Participation are
    surfaced; any parked/legacy type collapses to Phoenix (it still prices from its
    stored fields via the Phoenix waterfall — this only affects the picker/menu). */
export function detectNoteType(t: NoteTerms): NoteType {
  if (t.note_type === 'participation' || (t.capital_guarantee ?? 0) > 0) return 'participation'
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
    // ── Parked presets (not in NOTE_TYPES; kept for reintroduction) ──
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
