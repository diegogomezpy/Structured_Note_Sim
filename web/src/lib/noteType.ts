/* Note-type presets — mirror app.py's note-type picker. A preset only forces the
   fields a structure hard-codes (e.g. a reverse convertible's coupon barrier = 0);
   it never hides anything, so every payoff feature stays editable afterwards. */
import type { NoteTerms } from '../api/types'

export type NoteType = 'phoenix' | 'reverse_conv' | 'growth_autocall' | 'capital_protected' | 'custom'

export const NOTE_TYPES: NoteType[] = ['phoenix', 'reverse_conv', 'growth_autocall', 'capital_protected', 'custom']

/** Which preset a config most resembles (mirrors app.py:_detect_note_type).
    Order matters: the standalone capital-protected branch is checked first. */
export function detectNoteType(t: NoteTerms): NoteType {
  if ((t.capital_guarantee ?? 0) > 0) return 'capital_protected'
  if (t.coupon_at_autocall_only || (t.autocall_step_down ?? 0) > 0) return 'growth_autocall'
  if (t.coupon_barrier === 0 && !t.memory) return 'reverse_conv'
  return 'phoenix'
}

/** Return terms with the chosen structure's canonical fields forced; everything
    else (underlyings, maturity, coupon level, barriers) is preserved. */
export function applyPreset(t: NoteTerms, type: NoteType): NoteTerms {
  const n = { ...t }
  switch (type) {
    case 'capital_protected':
      n.coupon_pa = 0; n.coupon_barrier = 0; n.memory = false
      n.autocall_barrier = 2.0; n.autocall_basket = 'worst_of'; n.coupon_basket = 'worst_of'
      n.knock_in_barrier = 0; n.autocall_step_down = null; n.autocall_floor = null
      n.coupon_at_autocall_only = false; n.one_star_level = null
      n.capital_guarantee = (n.capital_guarantee ?? 0) > 0 ? n.capital_guarantee : 1.0
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
