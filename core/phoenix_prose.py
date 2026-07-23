"""Phoenix note description — three tight paragraphs, generated from terms.

Terse by design. The prose answers what an investor asks — what am I linked to
and for how long, what do I earn and when does it end early, what happens to my
capital — in three short paragraphs and no more. It is meant to be read in under
a minute and to fit in half a page; it is not a term sheet.

The rule that shapes everything here: **an optional feature is ONE clause folded
into the sentence that owns its mechanic — it never adds a sentence of its own,
and never a labelled fragment.** A step-down becomes a relative clause on the
autocall level; One Star becomes a limb on the test it touches; Zenith becomes a
clause on the redemption. There are no worked examples and no recitals.

Bilingual (en/es). The description is served from the API — there is no second
implementation in the front end. `tests/test_note_description.py` guards the
rules across every config in both languages.
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


# ── the three paragraphs ─────────────────────────────────────────────────────
# Each optional feature is one clause inside these; none adds a sentence of its
# own, and none opens a paragraph with a labelled fragment.

def _ac_level(c: Ctx) -> str:
    """The Autocall level as a short noun phrase. A step-down lives HERE, as a
    relative clause on the level — never as a sentence of its own."""
    if not c.declines:
        lvl = pct(c.ac[c.start - 1], c.lang)
        return (f"el nivel de Autocall del {lvl} del Nivel Inicial" if c.es
                else f"the Autocall level of {lvl} of strike")
    start = pct(c.ac_elig[0], c.lang)
    step = pct(c.step, c.lang).rstrip("%")
    if c.floor_idx:
        tail = (f" hasta un suelo del {pct(c.floor, c.lang)}" if c.es
                else f" to a floor of {pct(c.floor, c.lang)}")
    elif c.zero_idx:
        tail = (" hasta cero, tras lo cual la amortización es automática" if c.es
                else " to zero, after which a call becomes automatic")
    else:
        tail = (f" hasta el {pct(c.ac[-1], c.lang)} en la fecha final" if c.es
                else f" to {pct(c.ac[-1], c.lang)} at the final date")
    return (f"el nivel de Autocall, que parte del {start} del Nivel Inicial y baja "
            f"{step} puntos en cada fecha{tail}" if c.es else
            f"the Autocall level, which starts at {start} of strike and steps down "
            f"{step} points each date{tail}")


def _prot(c: Ctx) -> str:
    """Capital-return qualifier: 'in full' / 'at 90% of nominal'."""
    if abs(c.prot - 1.0) < 1e-9:
        return "íntegro" if c.es else "in full"
    return (f"al {pct(c.prot, c.lang)} del nominal" if c.es
            else f"at {pct(c.prot, c.lang)} of nominal")


def _t1_what(c: Ctx) -> str:
    """What it is linked to, how long it runs, when it can be called."""
    if not c.multi:
        base = (f"Esta Nota está vinculada a {c.joined}; con un único Subyacente, cada "
                f"condición se mide sobre su nivel de cierre." if c.es else
                f"This Note is linked to {c.joined}; with a single Underlying every "
                f"condition is measured on its closing level.")
    elif c.cbask == c.abask:
        base = (f"Esta Nota está vinculada a {c.joined}, y cada condición se mide sobre "
                f"{c.worst}." if c.es else
                f"This Note is linked to {c.joined}, and every condition is measured on "
                f"{c.worst}.")
    else:
        base = (f"Esta Nota está vinculada a {c.joined}: el cupón se mide sobre "
                f"{c.basket(c.cbask)}, la amortización anticipada sobre {c.basket(c.abask)} "
                f"y el capital sobre {c.worst}." if c.es else
                f"This Note is linked to {c.joined}: the coupon is measured on "
                f"{c.basket(c.cbask)}, early redemption on {c.basket(c.abask)} and capital "
                f"on {c.worst}.")

    if c.n_obs == 1:
        cal = (f" Dura {duration(c.t.maturity, c.lang)} y se observa una sola vez, al "
               f"vencimiento." if c.es else
               f" It runs {duration(c.t.maturity, c.lang)} and is observed once, at "
               f"maturity.")
    elif c.callable_:
        cal = (f" Dura un máximo de {duration(c.t.maturity, c.lang)}, observada con "
               f"periodicidad {c.freq} en {num_word(c.n_obs, c.lang)} fechas y amortizable "
               f"desde la {ord_word(c.start, c.lang)}." if c.es else
               f" It runs a maximum of {duration(c.t.maturity, c.lang)}, observed {c.freq} "
               f"across {num_word(c.n_obs, c.lang)} dates and callable from the "
               f"{ord_word(c.start, c.lang)}.")
    else:
        cal = (f" Dura {duration(c.t.maturity, c.lang)}, observada con periodicidad "
               f"{c.freq} en {num_word(c.n_obs, c.lang)} fechas." if c.es else
               f" It runs {duration(c.t.maturity, c.lang)}, observed {c.freq} across "
               f"{num_word(c.n_obs, c.lang)} dates.")
    return base + cal


def _t2_income(c: Ctx) -> str:
    """What is earned, on what condition, and when the Note ends early."""
    # income
    if c.cao:
        inc = (f"No paga renta periódica: una prima del {pct(c.per, c.lang)} del nominal se "
               f"devenga en cada observación y se abona en un único pago solo si la Nota se "
               f"amortiza anticipadamente; mantenida hasta el vencimiento no paga prima." if c.es else
               f"It pays no periodic income: a premium of {pct(c.per, c.lang)} of nominal "
               f"accrues at each observation and is paid as a single sum only if the Note is "
               f"called; held to maturity it pays no premium.")
    elif c.t.coupon_pa <= 0:
        inc = ("No paga cupón; toda su rentabilidad procede de la amortización." if c.es
               else "It pays no coupon; its whole return comes from redemption.")
    else:
        if c.cb > 0:
            oslimb = ""
            if c.os_live and c.os_coupon:
                oslimb = (f", o si algún Subyacente cierra en o por encima del {pct(c.os, c.lang)}"
                          if c.es else
                          f", or if any single Underlying is at or above {pct(c.os, c.lang)}")
            cond = (f" siempre que {c.basket(c.cbask)} cierre en o por encima de la Barrera "
                    f"de Cupón del {pct(c.cb, c.lang)} del Nivel Inicial{oslimb}" if c.es else
                    f" whenever {c.basket(c.cbask)} closes at or above the Coupon Barrier of "
                    f"{pct(c.cb, c.lang)} of strike{oslimb}")
        else:
            cond = (" en todas las fechas, sin condición" if c.es
                    else " at every date, unconditionally")
        mem = ""
        if c.n_obs > 1 and c.cb > 0:
            mem = ((" Un cupón no pagado se difiere y se libera en la siguiente fecha que "
                    "cumpla la condición (efecto memoria)." if c.es else
                    " A missed coupon carries over and is released on the next date that "
                    "qualifies (memory effect).") if c.memory else
                   (" Un cupón no pagado se pierde, sin memoria." if c.es else
                    " A missed coupon is lost, with no memory."))
        inc = (f"Paga un cupón del {pct(c.t.coupon_pa, c.lang)} anual —{pct(c.per, c.lang)} "
               f"por observación—{cond}.{mem}" if c.es else
               f"It pays {pct(c.t.coupon_pa, c.lang)} p.a. — {pct(c.per, c.lang)} per "
               f"observation —{cond}.{mem}")

    # early redemption
    if not c.callable_:
        ac = (" No puede amortizarse anticipadamente y agota su plazo." if c.es
              else " It cannot be called early and runs its full term.")
    elif c.soft:
        ac = (f" En cada fecha puede amortizarse anticipadamente a la par —más cualquier "
              f"cupón entonces debido—; cuanto más se acerque {c.basket(c.abask)} a "
              f"{_ac_level(c)}, más probable es." if c.es else
              f" On each date it may redeem early at par — plus any coupon then due — the "
              f"likelier the closer {c.basket(c.abask)} sits to {_ac_level(c)}.")
    else:
        oslimb = ""
        if c.os_live and c.os_autocall:
            oslimb = (f", o si algún Subyacente cierra en o por encima del {pct(c.os, c.lang)} "
                      f"de su Nivel Inicial" if c.es else
                      f", or if any single Underlying is at or above {pct(c.os, c.lang)} of "
                      f"its strike")
        ac = (f" En cada fecha la Nota se amortiza anticipadamente a la par —más cualquier "
              f"cupón entonces debido— si {c.basket(c.abask)} cierra en o por encima de "
              f"{_ac_level(c)}{oslimb}." if c.es else
              f" On each date the Note redeems early at par — plus any coupon then due — if "
              f"{c.basket(c.abask)} closes at or above {_ac_level(c)}{oslimb}.")
    return inc + ac


def _t3_capital(c: Ctx, issuer: str | None) -> str:
    """What happens to capital, whether there is upside, and whose credit backs it."""
    iss = issuer or ("el Emisor" if c.es else "the Issuer")
    prot = _prot(c)

    if c.ki <= 0:
        cap = (f"El capital no está en riesgo de mercado: una Nota no amortizada devuelve el "
               f"capital {prot} al vencimiento." if c.es else
               f"Capital is not at market risk: an uncalled Note repays capital {prot} at "
               f"maturity.")
    else:
        ex = max(0.05, round((c.ki - 0.15) * 20) / 20)
        rescue = ""
        if c.os_live and c.rescue_live and not c.os_dominates:
            rescue = (f" —salvo que algún Subyacente cierre en o por encima del "
                      f"{pct(c.os, c.lang)} de su Nivel Inicial, la excepción One Star, que "
                      f"devuelve el capital pese a la perforación—" if c.es else
                      f" — unless a single Underlying closes at or above {pct(c.os, c.lang)} "
                      f"of strike, the One Star exception, which returns capital despite the "
                      f"breach —")
        cap = (f"El capital vuelve íntegro salvo que {c.worst} cierre por debajo de la "
               f"Barrera de Knock-in del {pct(c.ki, c.lang)} del Nivel Inicial en la Fecha "
               f"de Observación Final{rescue}. Es una prueba europea: solo cuenta el cierre "
               f"de ese día. Por debajo, la Nota amortiza ese nivel uno a uno —una pérdida "
               f"del {pct(1 - ex, c.lang)} si {c.worst} cierra al {pct(ex, c.lang)}—; en la "
               f"barrera o por encima devuelve el capital {prot}." if c.es else
               f"Capital comes back in full unless {c.worst} closes below the Knock-in "
               f"Barrier of {pct(c.ki, c.lang)} of strike on the Final Observation "
               f"Date{rescue}. The test is European — only that day's close counts. Below it "
               f"the Note repays that level one-for-one — a {pct(1 - ex, c.lang)} loss if "
               f"{c.worst} closes at {pct(ex, c.lang)} — and at or above it repays capital "
               f"{prot}.")

    if c.zenith:
        cp = ("sin tope" if c.es else "with no cap") if c.cap is None else (
            f"con un tope del {pct(c.cap, c.lang)} del nominal" if c.es
            else f"capped at {pct(c.cap, c.lang)} of nominal")
        up = (f" Por la característica Zenith, cada amortización con capital devuelto añade "
              f"además el {pct(c.rate, c.lang)} de cuanto la cesta relevante exceda de su "
              f"Nivel Inicial ({cp})." if c.es else
              f" Through the Zenith feature, each capital-returning redemption also adds "
              f"{pct(c.rate, c.lang)} of any amount by which the relevant basket stands "
              f"above strike ({cp}).")
    elif c.cao:
        up = (f" No hay participación al alza: lo máximo que puede pagar es el "
              f"{pct(c.max_coupons, c.lang)} del nominal, y solo si se amortiza." if c.es else
              f" There is no upside participation: the most it can pay is "
              f"{pct(c.max_coupons, c.lang)} of nominal, and only if it is called.")
    elif c.t.coupon_pa > 0:
        up = (f" No hay participación al alza: la rentabilidad es el flujo de cupones, como "
              f"máximo el {pct(c.max_coupons, c.lang)} del nominal en agregado." if c.es else
              f" There is no upside participation: the return is the coupon stream, at most "
              f"{pct(c.max_coupons, c.lang)} of nominal in aggregate.")
    else:
        up = (" No hay participación al alza." if c.es
              else " There is no upside participation.")

    credit = (f" Todos los importes dependen de la solvencia de {iss}." if c.es
              else f" All amounts depend on {iss}'s ability to pay.")
    return cap + up + credit


def describe_phoenix(terms, lang: str = "en", issuer: str | None = None) -> str:
    """The three paragraphs, joined by a blank line."""
    c = Ctx(terms, lang)
    out = "\n\n".join([_t1_what(c), _t2_income(c), _t3_capital(c, issuer)])
    if lang == "es":
        # Spanish contracts "de el"→"del" / "a el"→"al"; the noun phrases are
        # assembled from pieces, so fix the joins once at the end.
        out = out.replace(" de el ", " del ").replace(" a el ", " al ")
    return out
