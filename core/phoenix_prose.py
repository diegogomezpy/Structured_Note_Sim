"""Phoenix note description — six fixed paragraphs, generated from terms.

The prose answers, in order, the questions an investor actually asks: what am I
linked to, how long does it run, what do I earn, when does it end early, what
happens to my capital, and is there any upside. Those six paragraphs are ALWAYS
present and always in that order.

The rule that shapes everything here: **an optional feature rewrites the
sentence that owns its mechanic — it never adds one.** A step-down barrier
becomes a relative clause on the autocall level inside the early-redemption
sentence; One Star becomes a second limb on the tests it touches; Zenith becomes
a tail on the settlement clause. Nothing is ever appended as a labelled
fragment, because the previous version did exactly that and read as a glossary
stapled to a paragraph.

Bilingual (en/es). A TS mirror lives in `web/src/lib/noteDescription.ts` and must
produce byte-identical output — `tests/test_note_description.py` proves it.
"""
from __future__ import annotations

# ── formatting ───────────────────────────────────────────────────────────────

def pct(x: float, lang: str = "en") -> str:
    """Percent, trailing zeros trimmed. Spanish uses a decimal comma."""
    s = f"{x * 100:.2f}".rstrip("0").rstrip(".")
    return (s.replace(".", ",") if lang == "es" else s) + "%"


_NUM_EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
           "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
           "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
_NUM_ES = ["cero", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho",
           "nueve", "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis",
           "diecisiete", "dieciocho", "diecinueve", "veinte"]
_ORD_EN = ["", "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
           "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
           "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth",
           "nineteenth", "twentieth"]
_ORD_ES = ["", "primera", "segunda", "tercera", "cuarta", "quinta", "sexta", "séptima",
           "octava", "novena", "décima", "undécima", "duodécima", "decimotercera",
           "decimocuarta", "decimoquinta", "decimosexta", "decimoséptima",
           "decimoctava", "decimonovena", "vigésima"]


def num_word(n: int, lang: str) -> str:
    """Counts up to twenty read as words; above that, digits."""
    if 0 <= n <= 20:
        return (_NUM_ES if lang == "es" else _NUM_EN)[n]
    return str(n)


def ord_word(n: int, lang: str) -> str:
    """Ordinals up to twentieth as words; above that, 24th / 24.ª."""
    if 1 <= n <= 20:
        return (_ORD_ES if lang == "es" else _ORD_EN)[n]
    if lang == "es":
        return f"{n}.ª"
    suf = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def freq_word(freq: str, lang: str) -> str:
    """Lower-case adjectival — it is dropped mid-sentence, never capitalised."""
    es = {"monthly": "mensual", "quarterly": "trimestral",
          "semi-annual": "semestral", "annual": "anual"}
    en = {"monthly": "monthly", "quarterly": "quarterly",
          "semi-annual": "semi-annual", "annual": "annual"}
    m = es if lang == "es" else en
    return m.get(freq, m["quarterly"])


def join_names(names: list[str], lang: str) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    conj = "y" if lang == "es" else "and"
    return f"{', '.join(names[:-1])} {conj} {names[-1]}"


def duration(maturity: float, lang: str) -> str:
    """Tenors are quoted in months throughout the app, prose included."""
    m = round(maturity * 12)
    if lang == "es":
        return "1 mes" if m == 1 else f"{m} meses"
    return "1 month" if m == 1 else f"{m} months"


# ── context ──────────────────────────────────────────────────────────────────

class Ctx:
    """Everything the paragraphs need, computed once and never recomputed.

    Deriving these up front is what keeps the templates readable and stops the
    same figure being recomputed (and formatted differently) in two places.
    """

    def __init__(self, terms, lang: str):
        self.t, self.lang = terms, lang
        self.es = lang == "es"
        names = list((terms.tickers or {}).values())
        self.names = names
        self.n_assets = len(names)
        self.multi = self.n_assets > 1
        self.joined = join_names(names, lang)
        self.n_obs = max(1, int(terms.n_obs))
        self.per = terms.coupon_rate
        self.months = round(terms.maturity * 12)
        self.freq = freq_word(terms.payment_freq, lang)
        self.ac = [float(x) for x in terms.autocall_barrier_schedule()]
        self.start = max(1, int(terms.autocall_start_period))
        self.callable_ = self.start <= self.n_obs
        self.ac_elig = self.ac[self.start - 1:] if self.callable_ else []
        self.step = float(getattr(terms, "autocall_step_down", 0.0) or 0.0)
        self.floor = getattr(terms, "autocall_floor", None)
        self.declines = bool(self.step > 0 and len(self.ac_elig) > 1
                             and self.ac_elig[-1] < self.ac_elig[0])
        self.floor_idx = None
        if self.declines and self.floor is not None:
            for i in range(self.start, self.n_obs + 1):
                if abs(self.ac[i - 1] - self.floor) < 1e-9:
                    self.floor_idx = i
                    break
        self.held_after = (self.n_obs - self.floor_idx) if self.floor_idx else 0
        self.zero_idx = None
        if self.declines:
            for i in range(self.start, self.n_obs + 1):
                if self.ac[i - 1] <= 0:
                    self.zero_idx = i
                    break
        self.max_coupons = self.n_obs * self.per
        self.cao = bool(getattr(terms, "coupon_at_autocall_only", False))
        self.memory = bool(terms.memory)
        self.cb = terms.coupon_barrier
        self.ki = terms.knock_in_barrier
        self.same_barrier = abs(self.cb - self.ki) < 1e-9
        self.prot = getattr(terms, "principal_protection", 1.0)
        self.zenith = bool(getattr(terms, "zenith", False))
        self.rate = getattr(terms, "participation_rate", 1.0) or 1.0
        self.cap = getattr(terms, "upside_cap", None)
        self.soft = getattr(terms, "call_steepness", None) is not None
        self.cbask = terms.coupon_basket
        self.abask = terms.autocall_basket

        # ── One Star reachability (spec §5.6) ────────────────────────────────
        os_lvl = terms.one_star_level
        self.os = os_lvl
        self.os_coupon = bool(terms.one_star_coupon)
        self.os_autocall = bool(terms.one_star_autocall)
        self.os_live = False        # name the feature at all
        self.rescue_live = False    # the maturity rescue can actually fire
        if os_lvl is not None and self.multi:
            self.os_live = True
            # (c) an autocall overlay at/below the final autocall level ends the
            # note there instead of rescuing it, so prob_rescued is identically 0
            unreachable = (self.os_autocall and self.callable_
                           and os_lvl <= self.ac[self.n_obs - 1] + 1e-12)
            self.rescue_live = not unreachable
            self.rescue_unreachable = unreachable
        else:
            self.rescue_unreachable = False
        # (d) single underlying: best_of == worst_of, so the rescue is vacuous
        self.os_dominates = (self.os_live and self.os is not None
                             and self.os <= self.ki + 1e-12)

        # Whether a call necessarily carries that observation's coupon (§5.4).
        self.coupon_at_call = (self.cb <= 0) or (
            self.cbask == self.abask
            and (min(self.ac_elig) if self.ac_elig else 1.0) >= self.cb - 1e-12
            and (not self.os_autocall or self.os_coupon)
        )

    # ── noun phrases ─────────────────────────────────────────────────────────
    def assets(self, plural: bool = True) -> str:
        if self.es:
            return "los Subyacentes" if plural else "el Subyacente"
        return "the Underlyings" if plural else "the Underlying"

    def basket(self, kind: str) -> str:
        """The noun phrase for a basket rule, with number agreement."""
        if not self.multi:
            return "el Subyacente" if self.es else "the Underlying"
        n = num_word(self.n_assets, self.lang)
        if self.es:
            return {"worst_of": f"el peor de los {n}", "best_of": f"el mejor de los {n}",
                    "average": f"el promedio de los {n}"}.get(kind, f"el peor de los {n}")
        return {"worst_of": f"the worst of the {n}", "best_of": f"the best of the {n}",
                "average": f"the average of the {n}"}.get(kind, f"the worst of the {n}")

    @property
    def worst(self) -> str:
        return self.basket("worst_of")


# ── the six paragraphs ───────────────────────────────────────────────────────
# Each returns one paragraph. Optional features rewrite sentences INSIDE these;
# none of them ever appends a paragraph of its own.

def _p1_exposure(c: Ctx) -> str:
    """What am I linked to, and whose performance decides each test."""
    if not c.multi:
        if c.es:
            s = (f"Esta Nota está vinculada al rendimiento de {c.joined}, el Subyacente. "
                 f"Al haber un único Subyacente no existe regla de cesta: todas las "
                 f"condiciones de la Nota se miden sobre su nivel de cierre.")
        else:
            s = (f"This Note is linked to the performance of {c.joined}, the Underlying. "
                 f"With a single Underlying there is no basket rule: every condition in "
                 f"the Note is measured on its closing level.")
        return s

    same = c.cbask == c.abask
    if c.es:
        if same:
            s = (f"Esta Nota está vinculada al rendimiento de {c.joined}. Todas sus "
                 f"condiciones se miden sobre {c.basket(c.cbask)}, no sobre la media de "
                 f"la cartera.")
        else:
            s = (f"Esta Nota está vinculada al rendimiento de {c.joined}. El cupón se "
                 f"decide sobre {c.basket(c.cbask)} y la amortización anticipada sobre "
                 f"{c.basket(c.abask)}, mientras que la barrera de capital se mide "
                 f"siempre sobre {c.worst}.")
        if c.cbask == "average" or c.abask == "average":
            s += (" Un valor fuerte compensa realmente a uno débil, pero solo en las "
                  "condiciones que usan el promedio.")
        elif same and c.cbask == "worst_of":
            otros = ("el otro" if c.n_assets == 2 else "los demás")
            s += (f" Basta con que ese Subyacente incumpla un nivel para que la condición "
                  f"no se cumpla, por bien que se comporte {otros}.")
    else:
        if same:
            s = (f"This Note is linked to the performance of {c.joined}. Every one of its "
                 f"conditions is measured on {c.basket(c.cbask)}, not on the average of "
                 f"the holding.")
        else:
            s = (f"This Note is linked to the performance of {c.joined}. The coupon is "
                 f"decided on {c.basket(c.cbask)} and early redemption on "
                 f"{c.basket(c.abask)}, while the capital barrier is always measured on "
                 f"{c.worst}.")
        if c.cbask == "average" or c.abask == "average":
            s += (" A strong performer genuinely offsets a weak one — but only for the "
                  "conditions that use the average.")
        elif same and c.cbask == "worst_of":
            others = ("the other Underlying performs" if c.n_assets == 2
                      else "the others perform")
            s += (f" It takes only that one Underlying to miss a level for the condition "
                  f"to fail, however well {others}.")

    if c.os_live:
        scope = _os_scope(c)
        if c.es:
            s += (f" Esta Nota matiza esa regla con la excepción One Star fijada en el "
                  f"{pct(c.os, c.lang)} del Nivel Inicial, que opera en sentido contrario: "
                  f"basta con que un solo Subyacente esté en ese nivel o por encima para "
                  f"dar por cumplida la condición. La excepción alcanza a {scope}.")
        else:
            s += (f" That rule is qualified by the One Star exception, set at "
                  f"{pct(c.os, c.lang)} of Strike, which works the other way: a single "
                  f"Underlying at or above that level is enough on its own to satisfy the "
                  f"condition. The exception reaches {scope}.")
    return s


def _os_scope(c: Ctx) -> str:
    """Which tests the One Star exception reaches, given its two scope flags."""
    mat = c.rescue_live
    if c.es:
        parts = []
        if c.os_coupon:
            parts.append("el cupón")
        if c.os_autocall:
            parts.append("la amortización anticipada")
        if mat:
            parts.append("la devolución del capital al vencimiento")
        if not parts:
            return "ninguna condición"
        if len(parts) == 3:
            return ("las tres condiciones: el cupón, la amortización anticipada y la "
                    "devolución del capital al vencimiento")
        body = " y ".join(parts) if len(parts) > 1 else parts[0]
        missing = []
        if not c.os_coupon:
            missing.append("al cupón")
        if not c.os_autocall:
            missing.append("a la amortización anticipada")
        tail = f"; no afecta {' ni '.join(missing)}" if missing else ""
        if len(parts) == 1 and mat and not c.os_coupon and not c.os_autocall:
            return "únicamente la devolución del capital al vencimiento" + tail
        return body + tail
    parts = []
    if c.os_coupon:
        parts.append("the coupon")
    if c.os_autocall:
        parts.append("the early redemption")
    if mat:
        parts.append("the return of capital at maturity")
    if not parts:
        return "no condition"
    if len(parts) == 3:
        return ("all three tests — the coupon, the early redemption and the return of "
                "capital at maturity")
    missing = []
    if not c.os_coupon:
        missing.append("the coupon")
    if not c.os_autocall:
        missing.append("the early redemption")
    tail = f"; it does not affect {' or '.join(missing)}" if missing else ""
    if len(parts) == 1 and mat and not c.os_coupon and not c.os_autocall:
        return "the return of capital at maturity only" + tail
    return " and ".join(parts) + tail


def _p2_calendar(c: Ctx) -> str:
    """How long it runs and how often it is looked at."""
    iso = getattr(c.t, "issue_date", None)
    if c.n_obs == 1:
        if c.es:
            strike = f" desde su Fecha de Strike, el {iso}," if iso else ""
            return (f"La Nota tiene una duración de {duration(c.t.maturity, c.lang)}"
                    f"{strike} y se observa una sola vez, al término de ese plazo. Esa "
                    f"única fecha es a la vez la única Fecha de Observación y la Fecha de "
                    f"Observación Final, y en ella se decide todo lo que la Nota paga.")
        strike = f" from its Strike Date of {iso}" if iso else ""
        return (f"The Note runs for {duration(c.t.maturity, c.lang)}{strike} and is "
                f"observed once, at the end of that period. That single date is both the "
                f"only Observation Date and the Final Observation Date, and everything the "
                f"Note pays is decided on it.")

    nw = num_word(c.n_obs, c.lang)
    if c.es:
        strike = f" desde su Fecha de Strike, el {iso}," if iso else ""
        s = (f"La Nota tiene una duración máxima de {duration(c.t.maturity, c.lang)}"
             f"{strike} y se observa con periodicidad {c.freq}, lo que da {nw} Fechas de "
             f"Observación en total; la {ord_word(c.n_obs, c.lang)} es además la Fecha de "
             f"Observación Final. Ese calendario de {nw} fechas es todo el calendario de "
             f"la Nota: cada cupón se decide en una de ellas, la amortización anticipada "
             f"solo puede producirse en una de ellas y la prueba de capital se realiza en "
             f"la última.")
        if c.callable_:
            s += (f" Dado que la Nota puede amortizarse a partir de la "
                  f"{ord_word(c.start, c.lang)} Fecha de Observación, los {c.months} meses "
                  f"son un techo de su vida y no una expectativa.")
        return s
    strike = f" from its Strike Date of {iso}" if iso else ""
    s = (f"The Note runs for a maximum of {duration(c.t.maturity, c.lang)}{strike} and is "
         f"observed {c.freq}, which gives {nw} Observation Dates in all; the "
         f"{ord_word(c.n_obs, c.lang)} is also the Final Observation Date. Those {nw} "
         f"dates are the whole of the Note's calendar: every coupon is decided on one of "
         f"them, early redemption can only happen on one of them, and the capital test is "
         f"performed on the last of them.")
    if c.callable_:
        s += (f" Because the Note can be called from the {ord_word(c.start, c.lang)} "
              f"Observation Date onwards, {c.months} months is a ceiling on its life "
              f"rather than an expectation.")
    return s


def _p3_income(c: Ctx) -> str:
    """What is paid, when it is withheld, whether it comes back.

    Never mentions the call — that fact belongs to P4's settlement sentence —
    and never repeats the frequency adjective, which P2 already established.
    """
    if c.cao:
        if c.es:
            return (f"La Nota no paga rentas periódicas. En su lugar, una prima del "
                    f"{pct(c.per, c.lang)} del nominal se devenga en cada Fecha de "
                    f"Observación desde la primera, y el total devengado se abona en un "
                    f"único pago solo si la Nota se amortiza anticipadamente. Si la Nota "
                    f"llega a la Fecha de Observación Final sin amortizarse, no se paga "
                    f"prima alguna: una Nota mantenida hasta el vencimiento no genera "
                    f"renta, con independencia del comportamiento de {c.assets()}.")
        return (f"The Note pays no periodic income. Instead a premium of "
                f"{pct(c.per, c.lang)} of nominal accrues at each Observation Date from "
                f"the first, and the whole amount accrued is paid in a single sum only if "
                f"the Note redeems early. If the Note reaches the Final Observation Date "
                f"without being called, no premium is paid at all: a Note held to maturity "
                f"earns no income, whatever {c.assets()} have done.")

    if c.t.coupon_pa <= 0:
        if c.es:
            return ("La Nota no paga cupón alguno. Toda su rentabilidad, si la hay, "
                    "procede de los importes de amortización que se describen más abajo.")
        return ("The Note pays no coupon. Its entire return, if any, comes from the "
                "redemption amounts described below.")

    if c.es:
        s = (f"La Nota paga un cupón del {pct(c.t.coupon_pa, c.lang)} anual, que se "
             f"fracciona en un cupón del {pct(c.per, c.lang)} del nominal por Fecha de "
             f"Observación.")
    else:
        s = (f"The Note pays income of {pct(c.t.coupon_pa, c.lang)} p.a., which divides "
             f"into a coupon of {pct(c.per, c.lang)} of nominal per Observation Date.")

    if c.cb <= 0:
        if c.es:
            s += (f" El cupón es incondicional: se paga en todas las Fechas de "
                  f"Observación hasta la de amortización inclusive, con independencia del "
                  f"comportamiento de {c.assets()}.")
        else:
            s += (f" The coupon is unconditional: it is paid at every Observation Date up "
                  f"to and including the one on which the Note redeems, whatever "
                  f"{c.assets()} have done.")
        return s

    limb = ""
    if c.os_live and c.os_coupon:
        limb = (f", o cuando cualquiera de los Subyacentes cierre en o por encima del "
                f"{pct(c.os, c.lang)} de su Nivel Inicial; cualquiera de las dos "
                f"condiciones basta por sí sola" if c.es else
                f", or when any single Underlying closes at or above {pct(c.os, c.lang)} "
                f"of its Strike level; either condition alone suffices")
    if c.es:
        s += (f" Se trata de una rentabilidad condicionada y no de un rendimiento "
              f"asegurado: el cupón se paga siempre que {c.basket(c.cbask)} cierre en o "
              f"por encima de la Barrera de Cupón del {pct(c.cb, c.lang)} de su Nivel "
              f"Inicial —justo en la barrera también paga{limb}— y no se abona en "
              f"aquellas observaciones en las que no se cumpla esa condición.")
    else:
        s += (f" It is a conditional rate rather than a yield: the coupon is paid whenever "
              f"{c.basket(c.cbask)} closes at or above the Coupon Barrier of "
              f"{pct(c.cb, c.lang)} of its Strike level — exactly at the barrier still "
              f"pays{limb} — and is withheld at any observation where that condition is "
              f"not met.")
    if c.os_live and c.os_coupon and c.os is not None and c.os < c.cb:
        s += (" Al situarse el nivel One Star por debajo de la Barrera de Cupón, en la "
              "práctica el límite determinante es el de One Star." if c.es else
              " Because the One Star level sits below the Coupon Barrier, the One Star "
              "limb is the binding test in practice.")

    if c.n_obs > 1:
        if c.memory:
            s += (" El cupón no pagado queda diferido, no perdido: por el efecto memoria "
                  "se acumula, y la primera Fecha de Observación posterior que cumpla la "
                  "condición libera todo lo pendiente junto con el cupón corriente. Ese "
                  "diferimiento vale lo que valga esa fecha posterior: si ninguna "
                  "observación restante la cumple, los cupones acumulados no llegan a "
                  "pagarse." if c.es else
                  " A withheld coupon is deferred rather than lost: under the memory "
                  "effect it accumulates, and the first later Observation Date that meets "
                  "the condition releases the whole backlog together with the coupon then "
                  "due. The deferral is only as good as that later date: if no remaining "
                  "observation meets it, the accumulated coupons are never paid.")
        else:
            s += (" No hay efecto memoria: el cupón no abonado en una observación se "
                  "pierde y no puede recuperarse en ninguna fecha posterior." if c.es else
                  " There is no memory: a coupon withheld at one observation is lost and "
                  "cannot be recovered on any later date.")
    return s


def _ac_level_phrase(c: Ctx) -> str:
    """The autocall level as a noun phrase — the step-down lives HERE, as a
    relative clause on the level, not as a paragraph of its own."""
    if not c.declines:
        return (f"el nivel de Autocall, fijo en el {pct(c.ac[c.start - 1], c.lang)} del "
                f"Nivel Inicial durante todo el plazo" if c.es else
                f"the Autocall level, fixed at {pct(c.ac[c.start - 1], c.lang)} of Strike "
                f"for the whole term")
    head = (f"el nivel de Autocall de esa fecha, que no es fijo: arranca en el "
            f"{pct(c.ac_elig[0], c.lang)} del Nivel Inicial en la "
            f"{ord_word(c.start, c.lang)} Fecha de Observación y baja "
            f"{pct(c.step, c.lang).rstrip('%')} puntos en cada fecha posterior" if c.es else
            f"the Autocall level for that date, which is not fixed: it starts at "
            f"{pct(c.ac_elig[0], c.lang)} of Strike on the {ord_word(c.start, c.lang)} "
            f"Observation Date and falls {pct(c.step, c.lang).rstrip('%')} points at each "
            f"date thereafter")
    if c.floor_idx:
        return head + (f" hasta alcanzar su suelo del {pct(c.floor, c.lang)} en la "
                       f"{ord_word(c.floor_idx, c.lang)} Fecha de Observación, donde se "
                       f"mantiene durante las {num_word(c.held_after, c.lang)} fechas "
                       f"restantes" if c.es else
                       f", reaching its floor of {pct(c.floor, c.lang)} at the "
                       f"{ord_word(c.floor_idx, c.lang)} Observation Date and holding "
                       f"there for the remaining {num_word(c.held_after, c.lang)} dates")
    if c.zero_idx:
        return head + (f" y llega a cero en la {ord_word(c.zero_idx, c.lang)} Fecha de "
                       f"Observación, momento a partir del cual la amortización "
                       f"anticipada es automática" if c.es else
                       f" and reaches zero at the {ord_word(c.zero_idx, c.lang)} "
                       f"Observation Date, from which point early redemption is automatic")
    if c.floor is not None:
        return head + (f" y termina en el {pct(c.ac[-1], c.lang)} en la Fecha de "
                       f"Observación Final; su suelo declarado del {pct(c.floor, c.lang)} "
                       f"nunca llega a alcanzarse" if c.es else
                       f", ending at {pct(c.ac[-1], c.lang)} at the Final Observation "
                       f"Date; its stated floor of {pct(c.floor, c.lang)} is never reached")
    return head + (f" y termina en el {pct(c.ac[-1], c.lang)} en la Fecha de Observación "
                   f"Final, sin suelo alguno" if c.es else
                   f", ending at {pct(c.ac[-1], c.lang)} at the Final Observation Date, "
                   f"with no floor beneath it")


def _p4_early(c: Ctx) -> str:
    """When it can end early, at what level, and what that settles."""
    if not c.callable_:
        return ("La Nota no puede amortizarse anticipadamente. Su primera fecha exigible "
                "es posterior a la Fecha de Observación Final, por lo que la amortización "
                "anticipada nunca puede producirse y la Nota agota necesariamente su "
                "plazo." if c.es else
                "The Note cannot be called early. Its first callable Observation Date "
                "falls after the Final Observation Date, so early redemption can never "
                "occur and the Note necessarily runs its full term.")

    # lock-up
    if c.start == 1:
        s = ("La amortización anticipada es posible desde la primera Fecha de "
             "Observación, de modo que no existe período de carencia." if c.es else
             "Early redemption is possible from the first Observation Date, so there is "
             "no lock-up.")
    else:
        k = num_word(c.start - 1, c.lang)
        mth = round(c.start * 12 / c.t.periods_per_year)
        kind = (("solo de devengo: la prima se acumula pero la Nota no puede amortizarse")
                if c.cao else "solo de cupón") if c.es else \
               (("accrual-only — the premium accrues but the Note cannot be called")
                if c.cao else "coupon-only")
        s = (f"Las {k} primeras Fechas de Observación son {kind}: la Nota no puede "
             f"amortizarse antes de la {ord_word(c.start, c.lang)}, es decir, antes de que "
             f"transcurran {mth} meses desde la Fecha de Strike." if c.es else
             f"The first {k} Observation Dates are {kind}: the Note cannot be called "
             f"before the {ord_word(c.start, c.lang)}, {mth} months after the Strike Date.")

    lvl = _ac_level_phrase(c)
    os_limb = ""
    if c.os_live and c.os_autocall:
        os_limb = (f", o si cualquiera de los Subyacentes cierra en o por encima del "
                   f"{pct(c.os, c.lang)} de su Nivel Inicial" if c.es else
                   f", or if any single Underlying closes at or above "
                   f"{pct(c.os, c.lang)} of its Strike level")
    if c.soft:
        s += (f" En cada una de esas fechas la Nota puede amortizarse anticipadamente por "
              f"referencia a {lvl}. El disparador es gradual y no absoluto: cuanto más "
              f"cerca cierre {c.basket(c.abask)} de ese nivel, más probable es la "
              f"amortización." if c.es else
              f" On each of those dates the Note may redeem early by reference to {lvl}. "
              f"The trigger is graduated rather than absolute: the closer "
              f"{c.basket(c.abask)} closes to that level the more likely the redemption.")
    else:
        s += (f" En cada una de esas fechas la Nota se amortiza anticipadamente si "
              f"{c.basket(c.abask)} cierra en o por encima de {lvl}{os_limb}." if c.es else
              f" On each of those dates the Note redeems early if {c.basket(c.abask)} "
              f"closes at or above {lvl}{os_limb}.")

    # step-down consequence — strictly about the LEVEL, never duration or income
    if c.declines:
        idx = c.floor_idx or c.n_obs
        lv = c.floor if c.floor_idx else c.ac[-1]
        s += (f" A partir de la {ord_word(idx, c.lang)} Fecha de Observación basta con que "
              f"{c.basket(c.abask)} cierre en el {pct(lv, c.lang)} de su Nivel Inicial "
              f"para que la Nota se amortice." if c.es else
              f" From the {ord_word(idx, c.lang)} Observation Date onwards "
              f"{c.basket(c.abask)} need only close at {pct(lv, c.lang)} of its Strike "
              f"level for the Note to be called.")

    # settlement — the only place the coupon-at-the-call fact is stated
    pay = []
    if c.cao:
        pay.append("la totalidad de la prima devengada hasta esa fecha" if c.es
                   else "the whole premium accrued to that date")
    elif c.t.coupon_pa > 0:
        if c.coupon_at_call:
            pay.append(("el cupón de esa observación y los cupones retenidos en memoria"
                        if c.memory else "el cupón de esa observación") if c.es else
                       ("that observation's coupon and any coupons held in memory"
                        if c.memory else "that observation's coupon"))
        else:
            forfeit = (" y hace perder toda la memoria acumulada" if c.memory else "") if c.es \
                      else (" and forfeits the whole accumulated memory" if c.memory else "")
            pay.append(f"el cupón que corresponda a esa observación conforme a la "
                       f"condición anterior: una amortización en una fecha en la que esa "
                       f"condición no se cumpla no paga cupón alguno{forfeit}" if c.es else
                       f"any coupon due for that observation under the condition above — a "
                       f"call on a date where that condition is not met pays no coupon"
                       f"{forfeit}")
    if c.zenith:
        capc = ("" if c.cap is None else
                (f", con un máximo del {pct(c.cap, c.lang)} del nominal, de modo que una "
                 f"amortización anticipada no puede superar el {pct(1 + c.cap, c.lang)} "
                 f"antes de cupones" if c.es else
                 f", subject to a maximum of {pct(c.cap, c.lang)} of nominal, so an early "
                 f"redemption cannot exceed {pct(1 + c.cap, c.lang)} before coupons"))
        if c.cap is None:
            capc = ", sin límite" if c.es else ", with no cap"
        pay.append(f"por la característica Zenith, el {pct(c.rate, c.lang)} de lo que "
                   f"{c.basket(c.abask)} exceda de su Nivel Inicial en esa fecha{capc}"
                   if c.es else
                   f"under the Zenith feature, {pct(c.rate, c.lang)} of any amount by "
                   f"which {c.basket(c.abask)} stands above its Strike level on that "
                   f"date{capc}")
    if pay:
        joined = (" y ".join(pay) if c.es else " and ".join(pay))
        s += (f" La amortización anticipada devuelve el capital a la par en efectivo, "
              f"junto con {joined}." if c.es else
              f" Early redemption repays capital at par in cash, together with {joined}.")
    else:
        s += (" La amortización anticipada devuelve el capital a la par en efectivo."
              if c.es else "Early redemption repays capital at par in cash.")

    if c.n_obs == 1 and c.start == 1:
        s += (" Al existir una única Fecha de Observación, la amortización anticipada y "
              "la prueba de vencimiento coinciden en el mismo día." if c.es else
              " Because there is only one Observation Date, an early redemption and the "
              "maturity test fall on the same day.")
    else:
        s += (" La Nota se extingue en ese momento: no se devengan más cupones y la "
              "prueba de capital al vencimiento no llega a realizarse." if c.es else
              " The Note then ceases to exist: no further coupons accrue and the capital "
              "test at maturity is never performed.")
    if c.rescue_unreachable:
        s += (" Un solo Subyacente en ese nivel o por encima pone fin a la Nota en lugar "
              "de rescatarla al vencimiento." if c.es else
              " A single Underlying at or above that level ends the Note rather than "
              "rescuing it at maturity.")
    return s


def _prot_phrase(c: Ctx, short: bool = False) -> str:
    if abs(c.prot - 1.0) < 1e-9:
        return "íntegro, al 100% del nominal" if c.es else "in full at 100% of nominal"
    base = (f"al {pct(c.prot, c.lang)} del nominal" if c.es
            else f"at {pct(c.prot, c.lang)} of nominal")
    if short:
        return base
    return base + (
        "; este nivel se aplica únicamente a una Nota que sobreviva hasta la Fecha de "
        "Observación Final —una amortización anticipada siempre devuelve la par— y no "
        "constituye un suelo en el tramo de pérdida" if c.es else
        " — this level applies only to a Note that survives to the Final Observation "
        "Date; an early redemption always repays par, and it is not a floor on the loss "
        "branch")


def _p5_capital(c: Ctx) -> str:
    """The single test that decides capital, and both of its branches."""
    if c.ki <= 0:
        return (f"El capital no está expuesto al comportamiento del mercado. No hay "
                f"barrera de knock-in: una Nota que llegue a la Fecha de Observación Final "
                f"sin amortizarse devuelve {_prot_phrase(c)}, con independencia del "
                f"comportamiento de {c.assets()}." if c.es else
                f"Capital is not at risk from market performance. There is no knock-in "
                f"barrier: a Note that reaches the Final Observation Date uncalled repays "
                f"{_prot_phrase(c)} whatever {c.assets()} have done.")

    rescue = c.os_live and c.rescue_live and not c.os_dominates
    if rescue:
        s = ("El capital solo está en riesgo si la Nota llega a la Fecha de Observación "
             "Final sin amortizarse, y aun entonces han de fallar dos condiciones a la "
             "vez." if c.es else
             "Capital is at risk only if the Note reaches the Final Observation Date "
             "uncalled, and even then two conditions must fail together.")
    else:
        s = ("El capital solo está en riesgo en un supuesto, y se comprueba en un único "
             "día." if c.es else
             "Capital is at risk in exactly one circumstance, and it is tested on one "
             "single day.")

    same = (" —el mismo nivel que rige el cupón—" if c.es
            else " — the same level that governs the coupon —") if c.same_barrier and c.cb > 0 else ""
    s += (f" Si la Nota no se ha amortizado anticipadamente, el nivel de cierre de "
          f"{c.worst} en la Fecha de Observación Final se compara con la Barrera de "
          f"Knock-in del {pct(c.ki, c.lang)}{same} de su Nivel Inicial." if c.es else
          f" If the Note has not already redeemed early, the closing level of {c.worst} "
          f"on the Final Observation Date is compared with the Knock-in Barrier of "
          f"{pct(c.ki, c.lang)}{same} of its Strike level.")

    zen = ""
    if c.zenith:
        capm = (", sin límite" if c.es else ", with no cap") if c.cap is None else (
            f", con un máximo del {pct(c.cap, c.lang)} del nominal, de modo que la "
            f"amortización al vencimiento no puede superar el {pct(c.prot + c.cap, c.lang)} "
            f"antes de cupones" if c.es else
            f", subject to a maximum of {pct(c.cap, c.lang)} of nominal, so redemption at "
            f"maturity cannot exceed {pct(c.prot + c.cap, c.lang)} before coupons")
        zen = (f", junto con el {pct(c.rate, c.lang)} de lo que {c.worst} exceda de su "
               f"Nivel Inicial{capm}" if c.es else
               f", together with {pct(c.rate, c.lang)} of any amount by which {c.worst} "
               f"stands above its Strike level{capm}")
    s += (f" En ese nivel o por encima la barrera aguanta y el capital se devuelve "
          f"{_prot_phrase(c)}{zen}." if c.es else
          f" At or above it the barrier holds and capital is repaid {_prot_phrase(c)}"
          f"{zen}.")

    if rescue:
        nopart = (", si bien una amortización rescatada de este modo no lleva "
                  "participación alguna" if c.es else
                  ", though a redemption rescued in this way carries no participation") \
                 if c.zenith else ""
        s += (f" Segundo, debe fallar el rescate One Star: si cualquiera de los "
              f"Subyacentes cierra en o por encima del {pct(c.os, c.lang)} de su Nivel "
              f"Inicial, el capital se devuelve {_prot_phrase(c, short=True)} pese a la "
              f"perforación{nopart}. La pérdida exige, por tanto, que {c.worst} cierre por "
              f"debajo del {pct(c.ki, c.lang)} de su Nivel Inicial y que, el mismo día, "
              f"todos los Subyacentes cierren por debajo del {pct(c.os, c.lang)} del suyo."
              if c.es else
              f" Second, the One Star rescue must fail: if any single Underlying closes at "
              f"or above {pct(c.os, c.lang)} of its Strike level, capital is returned "
              f"{_prot_phrase(c, short=True)} despite the breach{nopart}. A loss therefore "
              f"requires {c.worst} to close below {pct(c.ki, c.lang)} of its Strike level "
              f"and every Underlying to close below {pct(c.os, c.lang)} of its own on the "
              f"same day.")

    ex = max(0.05, round((c.ki - 0.15) * 20) / 20)
    if not c.multi:
        offset = ""
    elif c.es:
        offset = (", y el buen comportamiento del otro Subyacente no la compensa"
                  if c.n_assets == 2 else
                  ", y el buen comportamiento de los demás Subyacentes no la compensa")
    else:
        offset = (", and a strong performance from the other Underlying does not offset it"
                  if c.n_assets == 2 else
                  ", and a strong performance from the other Underlyings does not offset it")
    lead = ("Cuando ambas fallan" if rescue else "Por debajo") if c.es else \
           ("Where both fail" if rescue else "Below it")
    s += (f" {lead} la Nota amortiza a ese Nivel Final uno a uno y sin suelo alguno: "
          f"{c.worst} al {pct(ex, c.lang)} de su Nivel Inicial devuelve el "
          f"{pct(ex, c.lang)} del nominal, una pérdida del {pct(1 - ex, c.lang)}{offset}."
          if c.es else
          f" {lead} the Note repays that final level one-for-one and with no floor: "
          f"{c.worst} at {pct(ex, c.lang)} of its Strike level returns {pct(ex, c.lang)} "
          f"of nominal, a loss of {pct(1 - ex, c.lang)}{offset}.")

    s += (f" Al tratarse de una barrera europea, nada de lo anterior cuenta: {c.worst} "
          f"puede cotizar muy por debajo de la barrera durante meses y, si cierra en ella "
          f"o por encima en la Fecha de Observación Final, el capital vuelve intacto." if c.es
          else
          f" Because the test is European, nothing before that day counts: {c.worst} may "
          f"trade far below the barrier for months and, provided it closes at or above it "
          f"on the Final Observation Date, capital comes back intact.")
    s += ((" Una Nota amortizada anticipadamente nunca se contrasta con la barrera; una "
           "Nota que llega a esta prueba no ha percibido, por definición, prima alguna."
           if c.es else
           " A Note that has redeemed early is never tested against the barrier; a Note "
           "that reaches this test has, by definition, received no premium.") if c.cao else
          (" Los cupones ya cobrados se conservan en todo caso y, en una Nota amortizada "
           "anticipadamente, la barrera nunca llega a mirarse." if c.es else
           " Coupons already paid are kept in every case, and on a Note that has redeemed "
           "early the barrier is never looked at."))
    return s


def _p6_upside(c: Ctx, issuer: str | None) -> str:
    """Whether there is participation, the aggregate ceiling, the credit."""
    iss = issuer or ("el Emisor" if c.es else "the Issuer")
    close = (f" Todos los importes son obligaciones no garantizadas de {iss} y dependen "
             f"de su capacidad de pago." if c.es else
             f" All amounts are unsecured obligations of {iss} and depend on its ability "
             f"to pay.")
    prot_num = pct(c.prot, c.lang)
    agg = pct(c.max_coupons, c.lang)

    if c.zenith:
        capp = ("sin límite alguno" if c.es else "with no cap") if c.cap is None else (
            f"con un máximo del {pct(c.cap, c.lang)} del nominal" if c.es
            else f"subject to a maximum of {pct(c.cap, c.lang)} of nominal")
        subj = c.worst if c.abask == "worst_of" else (
            f"{c.basket(c.abask)} en una amortización anticipada, y {c.worst} al "
            f"vencimiento" if c.es else
            f"{c.basket(c.abask)} on an early redemption, and {c.worst} at maturity")
        norescue = (", ni en una amortización rescatada por la excepción One Star" if c.es
                    else ", nor on a redemption rescued by the One Star exception") \
                   if (c.os_live and c.rescue_live) else ""
        if c.es:
            return (f"Esta Nota sí participa de la subida del mercado, a través de la "
                    f"característica Zenith. Siempre que se devuelva el capital —por "
                    f"amortización anticipada o al vencimiento con la barrera intacta— la "
                    f"Nota abona el {pct(c.rate, c.lang)} de lo que {subj} exceda de su "
                    f"Nivel Inicial en la fecha de amortización, {capp}, además del capital "
                    f"y de todos los cupones. Si ese nivel está en o por debajo de su Nivel "
                    f"Inicial, la participación es sencillamente cero. Los cupones no se "
                    f"ven afectados y siguen topando en un {agg} del nominal en agregado; "
                    f"la participación se suma a ellos y nunca aplica en el tramo de "
                    f"pérdida{norescue}." + close)
        return (f"This Note does participate in a rising market, through the Zenith "
                f"feature. Whenever capital is returned — on an early redemption or at "
                f"maturity with the barrier intact — the Note pays {pct(c.rate, c.lang)} "
                f"of any amount by which {subj} stands above its Strike level on the date "
                f"of redemption, {capp}, in addition to capital and to every coupon. If "
                f"that level is at or below its Strike level the participation is simply "
                f"zero. The coupons are unaffected and still cap at {agg} of nominal in "
                f"aggregate; the participation sits on top of them, and it never applies "
                f"on the loss branch{norescue}." + close)

    if c.cao:
        if c.es:
            return (f"La Nota no participa de la subida del mercado: la amortización es "
                    f"del {prot_num} del nominal por mucho que suban {c.assets()}. Toda su "
                    f"rentabilidad es la prima devengada, y la prima solo se abona en caso "
                    f"de amortización anticipada, de modo que lo máximo que la Nota puede "
                    f"pagar es el {agg} del nominal, mediante una amortización en la Fecha "
                    f"de Observación Final, y nada en absoluto si nunca se amortiza. "
                    f"Cuanto más tarde la amortización, mayor la prima." + close)
        return (f"The Note offers no participation in a rising market: redemption is "
                f"{prot_num} of nominal however far {c.assets()} climb. Its entire return "
                f"is the accrued premium, and the premium is paid only on an early "
                f"redemption — so the most the Note can pay is {agg} of nominal, on a call "
                f"at the Final Observation Date, and nothing at all if it is never called. "
                f"The later the call, the larger the premium." + close)

    if c.t.coupon_pa <= 0:
        return (f"La Nota no participa de la subida del mercado y no paga cupón: la "
                f"amortización es del {prot_num} del nominal por mucho que suban "
                f"{c.assets()}." + close if c.es else
                f"The Note offers no participation in a rising market and pays no coupon: "
                f"redemption is {prot_num} of nominal however far {c.assets()} climb."
                + close)

    life = ("mientras la Nota siga viva" if c.callable_ else
            f"a lo largo de los {c.months} meses completos") if c.es else \
           ("for as long as the Note remains outstanding" if c.callable_ else
            f"over the full {c.months} months")
    if c.es:
        return (f"La Nota no participa de la subida del mercado. Por mucho que suban "
                f"{c.assets()} por encima de su Nivel Inicial, la amortización es del "
                f"{prot_num} del nominal y nada más, de modo que toda la rentabilidad es "
                f"el flujo de cupones: como máximo el {pct(c.t.coupon_pa, c.lang)} anual "
                f"{life}, y un {agg} del nominal en agregado —"
                f"{num_word(c.n_obs, c.lang)} cupones del {pct(c.per, c.lang)}—. Ese techo "
                f"es precisamente lo que financia el cupón: la Nota está pensada para "
                f"rentar en un mercado lateral o moderadamente bajista, no para capturar "
                f"una subida." + close)
    return (f"The Note offers no participation in a rising market. However far "
            f"{c.assets()} climb above their Strike levels, redemption is {prot_num} of "
            f"nominal and no more, so the entire return is the coupon stream: at most "
            f"{pct(c.t.coupon_pa, c.lang)} p.a. {life}, and {agg} of nominal in aggregate "
            f"— {num_word(c.n_obs, c.lang)} coupons of {pct(c.per, c.lang)}. That ceiling "
            f"is what pays for the coupon: the Note is built to earn in a flat or "
            f"moderately falling market, not to capture a rally." + close)


def describe_phoenix(terms, lang: str = "en", issuer: str | None = None) -> str:
    """The six paragraphs, joined by a blank line."""
    c = Ctx(terms, lang)
    return "\n\n".join([
        _p1_exposure(c), _p2_calendar(c), _p3_income(c),
        _p4_early(c), _p5_capital(c), _p6_upside(c, issuer),
    ])
