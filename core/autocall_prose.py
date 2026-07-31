"""Autocall note description — two short paragraphs, generated from terms.

Deliberately terse. The features table beside it carries the numbers, so the
prose only has to say how the note WORKS: what it is linked to, what it pays
and when it autocalls (paragraph one), and what happens to capital (paragraph
two). Anything that reads as a recital, an aside or a worked example is cut.

Two rules shape it:

* **An optional feature is ONE clause folded into the sentence that owns its
  mechanic** — never a sentence of its own, never a labelled fragment, and
  never mentioned at all when the note does not use it.
* **Spanish says `autocancelar` / `autocancelación`, never `amortizar`** — the
  latter means repayment of principal, not an issuer call, and the app's own
  labels ("Barrera de autocancelación") already use the right word. Redemption
  is `devolver`.

Bilingual (en/es). Served from the API — there is no second implementation in
the front end. `tests/test_note_description.py` guards these rules across every
config in both languages.
"""
from __future__ import annotations

# ── formatting ───────────────────────────────────────────────────────────────

def pct(x: float, lang: str = "en") -> str:
    """Percent, trailing zeros trimmed. Spanish uses a decimal comma."""
    s = f"{x * 100:.2f}".rstrip("0").rstrip(".")
    return (s.replace(".", ",") if lang == "es" else s) + "%"


def num_word(n: int, lang: str) -> str:
    """Counts are rendered as digits, never spelled out — the descriptions read
    as figures ("18 dates", not "eighteen dates"). The lang argument is kept for
    a stable signature across the call sites."""
    return str(n)


def ord_word(n: int, lang: str) -> str:
    """Ordinals as digits too: 3.ª (es) / 3rd (en), never "tercera"/"third"."""
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
        self.months = terms.maturity_months     # one source — see effective_maturity
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


# ── the two paragraphs ───────────────────────────────────────────────────────

def _ac_level(c: Ctx) -> str:
    """The Autocall level as a short noun phrase. A step-down lives HERE, as a
    relative clause on the level — never as a sentence of its own."""
    if not c.declines:
        lvl = pct(c.ac[c.start - 1], c.lang)
        return (f"el nivel de Autocall del {lvl}" if c.es
                else f"the Autocall level of {lvl}")
    start = pct(c.ac_elig[0], c.lang)
    step = pct(c.step, c.lang).rstrip("%")
    if c.floor_idx:
        tail = (f" hasta un suelo del {pct(c.floor, c.lang)}" if c.es
                else f" to a floor of {pct(c.floor, c.lang)}")
    elif c.zero_idx:
        tail = (" hasta cero, tras lo cual la autocancelación es automática" if c.es
                else " to zero, after which the autocall becomes automatic")
    else:
        tail = (f" hasta el {pct(c.ac[-1], c.lang)} en la fecha final" if c.es
                else f" to {pct(c.ac[-1], c.lang)} at the final date")
    return (f"el nivel de Autocall, que parte del {start} y baja {step} puntos en cada "
            f"fecha{tail}" if c.es else
            f"the Autocall level, which starts at {start} and steps down {step} points "
            f"each date{tail}")


def _prot(c: Ctx) -> str:
    """Capital-return qualifier: 'in full' / 'at 90% of nominal'."""
    if abs(c.prot - 1.0) < 1e-9:
        return "íntegro" if c.es else "in full"
    return (f"al {pct(c.prot, c.lang)} del nominal" if c.es
            else f"at {pct(c.prot, c.lang)} of nominal")


def _t1_mechanics(c: Ctx) -> str:
    """What it is linked to, how long it runs, what it pays, when it autocalls."""
    # exposure
    if not c.multi:
        s = (f"Vinculada a {c.joined}; todas las condiciones se miden sobre su nivel de "
             f"cierre." if c.es else
             f"Linked to {c.joined}; every condition is measured on its closing level.")
    elif c.cbask == c.abask:
        s = (f"Vinculada a {c.joined}; todas las condiciones se miden sobre {c.worst}."
             if c.es else
             f"Linked to {c.joined}; every condition is measured on {c.worst}.")
    else:
        s = (f"Vinculada a {c.joined}: el cupón sobre {c.basket(c.cbask)}, la "
             f"autocancelación sobre {c.basket(c.abask)} y el capital sobre {c.worst}."
             if c.es else
             f"Linked to {c.joined}: the coupon on {c.basket(c.cbask)}, the autocall on "
             f"{c.basket(c.abask)} and capital on {c.worst}.")

    # calendar (+ when it first becomes callable)
    call_from = ""
    if c.callable_ and c.start > 1:
        call_from = (f", autocancelable desde la {ord_word(c.start, c.lang)}" if c.es
                     else f", callable from the {ord_word(c.start, c.lang)}")
    if c.n_obs == 1:
        s += (f" Dura {duration(c.t.maturity, c.lang)}, con una sola observación al "
              f"vencimiento." if c.es else
              f" It runs {duration(c.t.maturity, c.lang)}, with a single observation at "
              f"maturity.")
    else:
        s += (f" Dura {duration(c.t.maturity, c.lang)}, con observación {c.freq} en "
              f"{num_word(c.n_obs, c.lang)} fechas{call_from}." if c.es else
              f" It runs {duration(c.t.maturity, c.lang)}, observed {c.freq} across "
              f"{num_word(c.n_obs, c.lang)} dates{call_from}.")

    # income
    if c.cao:
        s += (f" No paga cupón periódico: una prima del {pct(c.per, c.lang)} se devenga en "
              f"cada observación y solo se abona si la Nota se autocancela." if c.es else
              f" It pays no periodic coupon: a {pct(c.per, c.lang)} premium accrues each "
              f"observation and is paid only if the Note autocalls.")
    elif c.t.coupon_pa > 0:
        if c.cb > 0:
            oslimb = ""
            if c.os_live and c.os_coupon:
                oslimb = (f", o algún Subyacente el {pct(c.os, c.lang)}" if c.es
                          else f", or any one Underlying is at {pct(c.os, c.lang)}")
            cond = (f" cuando {c.basket(c.cbask)} cierre en o por encima de la Barrera de "
                    f"Cupón del {pct(c.cb, c.lang)}{oslimb}" if c.es else
                    f" when {c.basket(c.cbask)} closes at or above the Coupon Barrier of "
                    f"{pct(c.cb, c.lang)}{oslimb}")
        else:
            cond = " en todas las fechas" if c.es else " at every date"
        mem = ""
        if c.n_obs > 1 and c.cb > 0:
            mem = ((", y un cupón no pagado se acumula (efecto memoria)" if c.es
                    else ", and a missed coupon carries over (memory effect)") if c.memory
                   else (", sin memoria" if c.es else ", with no memory"))
        s += (f" Paga un {pct(c.t.coupon_pa, c.lang)} anual ({pct(c.per, c.lang)} por "
              f"observación){cond}{mem}." if c.es else
              f" It pays {pct(c.t.coupon_pa, c.lang)} p.a. ({pct(c.per, c.lang)} per "
              f"observation){cond}{mem}.")
    else:
        s += (" No paga cupón." if c.es else " It pays no coupon.")

    # autocall
    if not c.callable_:
        s += (" No es autocancelable y agota su plazo." if c.es
              else " It cannot autocall and runs its full term.")
    elif c.soft:
        s += (f" Se autocancela a la par, con el cupón que corresponda, con probabilidad "
              f"creciente conforme {c.basket(c.abask)} se acerca a {_ac_level(c)}." if c.es else
              f" It autocalls at par, with any coupon then due, more likely the closer "
              f"{c.basket(c.abask)} sits to {_ac_level(c)}.")
    else:
        oslimb = ""
        if c.os_live and c.os_autocall:
            oslimb = (f", o algún Subyacente el {pct(c.os, c.lang)}" if c.es
                      else f", or any one Underlying reaches {pct(c.os, c.lang)}")
        s += (f" Se autocancela a la par, con el cupón que corresponda, en cuanto "
              f"{c.basket(c.abask)} cierre en o por encima de {_ac_level(c)}{oslimb}."
              if c.es else
              f" It autocalls at par, with any coupon then due, once {c.basket(c.abask)} "
              f"closes at or above {_ac_level(c)}{oslimb}.")
    return s


def _t2_capital(c: Ctx, issuer: str | None) -> str:
    """What happens to capital, whether there is upside, whose credit backs it."""
    iss = issuer or ("el Emisor" if c.es else "the Issuer")
    prot = _prot(c)

    if c.ki <= 0:
        s = (f"El capital no está en riesgo de mercado: una Nota no autocancelada devuelve "
             f"el capital {prot} al vencimiento." if c.es else
             f"Capital is not at market risk: a Note that is not autocalled repays capital "
             f"{prot} at maturity.")
    else:
        rescue = ""
        if c.os_live and c.rescue_live and not c.os_dominates:
            rescue = (f", salvo que algún Subyacente cierre en o por encima del "
                      f"{pct(c.os, c.lang)} (excepción One Star)" if c.es else
                      f", unless any one Underlying closes at or above {pct(c.os, c.lang)} "
                      f"(the One Star exception)")
        s = (f"El capital vuelve {prot} salvo que {c.worst} cierre por debajo de la Barrera "
             f"de Knock-in del {pct(c.ki, c.lang)} en la fecha final{rescue} —prueba europea: "
             f"solo cuenta ese cierre—; por debajo, la Nota devuelve ese nivel uno a uno."
             if c.es else
             f"Capital comes back {prot} unless {c.worst} closes below the Knock-in Barrier "
             f"of {pct(c.ki, c.lang)} on the final date{rescue} — a European test, so only "
             f"that close counts. Below it the Note repays that level one-for-one.")

    if c.zenith:
        cp = ("sin tope" if c.es else "with no cap") if c.cap is None else (
            f"con un tope del {pct(c.cap, c.lang)}" if c.es
            else f"capped at {pct(c.cap, c.lang)}")
        s += (f" Por la característica Zenith, toda devolución de capital añade el "
              f"{pct(c.rate, c.lang)} de cuanto la cesta exceda su Nivel Inicial ({cp})."
              if c.es else
              f" Through the Zenith feature, any return of capital also adds "
              f"{pct(c.rate, c.lang)} of whatever the basket stands above strike ({cp}).")
    elif c.cao:
        s += (f" No hay participación al alza: como máximo paga el "
              f"{pct(c.max_coupons, c.lang)}, y solo si se autocancela." if c.es else
              f" There is no upside participation: it pays at most "
              f"{pct(c.max_coupons, c.lang)}, and only if it autocalls.")
    elif c.t.coupon_pa > 0:
        s += (f" Los cupones son toda la rentabilidad, con un máximo del "
              f"{pct(c.max_coupons, c.lang)} del nominal en total." if c.es else
              f" The coupons are the entire return, capped at "
              f"{pct(c.max_coupons, c.lang)} of nominal in total.")

    s += (f" Todos los importes dependen de la solvencia de {iss}." if c.es
          else f" All amounts depend on {iss}'s ability to pay.")
    return s


def describe_autocall(terms, lang: str = "en", issuer: str | None = None) -> str:
    """The two paragraphs, joined by a blank line."""
    c = Ctx(terms, lang)
    out = "\n\n".join([_t1_mechanics(c), _t2_capital(c, issuer)])
    if lang == "es":
        # Spanish contracts "de el"→"del" / "a el"→"al"; the noun phrases are
        # assembled from pieces, so fix the joins once at the end.
        out = out.replace(" de el ", " del ").replace(" a el ", " al ")
    return out
