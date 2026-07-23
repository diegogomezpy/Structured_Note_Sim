"""Systematic, terms-driven note description — the "Esta Inversión (la Nota)…"
prose blurb that fills itself out from a note's terms.

Pure function of NoteTerms: no I/O, no Streamlit. Used by the PDF report and
exposed via the API. Bilingual (en/es). A TS mirror lives in
``web/src/lib/noteDescription.ts`` for the live web display — keep the two in
sync if the template changes.
"""
from __future__ import annotations


def _pct(x: float) -> str:
    """Percent with trailing zeros trimmed — 0.1 -> '10%', 0.055 -> '5.5%'.
    Matches p2() in the TS mirror; the two must format identically or the web
    and the PDF quote the same note differently."""
    return f"{x * 100:.2f}".rstrip("0").rstrip(".") + "%"


def _fmt_duration(maturity: float, lang: str) -> str:
    """Tenors are quoted in MONTHS throughout the app, prose included — the TS
    mirror does the same, and the two must agree or the web and the PDF describe
    the same note differently."""
    months = round(maturity * 12)
    if lang == "es":
        return "1 mes" if months == 1 else f"{months} meses"
    return "1 month" if months == 1 else f"{months} months"


def _freq_word(freq: str, lang: str) -> str:
    es = {"monthly": "Mensual", "quarterly": "Trimestral",
          "semi-annual": "Semestral", "annual": "Anual"}
    en = {"monthly": "monthly", "quarterly": "quarterly",
          "semi-annual": "semi-annual", "annual": "annual"}
    return (es if lang == "es" else en).get(freq, es["quarterly"] if lang == "es" else "quarterly")


def _join_names(names: list[str], lang: str) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    conj = "y" if lang == "es" else "and"
    return f"{', '.join(names[:-1])} {conj} {names[-1]}"


def _describe_participation(terms, lang, names, multi) -> str:
    """Prose for a Participation Note (a maturity payoff profile, no coupons)."""
    dur = _fmt_duration(terms.maturity, lang)
    joined = _join_names(names, lang)
    _p = _pct
    prot, rate = terms.protection_level or 0.0, terms.participation_rate or 0.0
    strike, cap = terms.participation_strike or 1.0, terms.upside_cap
    pd, pu = terms.participation_downside, terms.participation_upside

    # Periodic / cliquet — a series of back-to-back protected participation notes.
    if getattr(terms, "participation_periodic", False):
        freq = _freq_word(terms.payment_freq, lang)
        pcap = terms.period_cap
        if lang == "es":
            bw = {"worst_of": "el peor rendimiento", "best_of": "el mejor rendimiento",
                  "average": "el rendimiento promedio"}.get(terms.participation_basket, "el rendimiento")
            subj = "los Subyacentes" if multi else "el Subyacente"
            capph = f" (limitada al {_p(pcap)} por período)" if pcap is not None else ""
            return (f"Esta Nota está vinculada a {bw} de {joined}, {subj}, con una duración de {dur}. "
                    f"En cada fecha de reinicio {freq} paga el {_p(rate)} de la subida de ese período{capph}; "
                    f"los períodos a la baja no pagan nada y el strike se reinicia. El capital está protegido al "
                    f"{_p(min(prot, 1.0))} al vencimiento.")
        bw = {"worst_of": "the worst-performing", "best_of": "the best-performing",
              "average": "the average"}.get(terms.participation_basket, "the")
        subj = "the Underlyings" if multi else "the Underlying"
        capph = f" (capped at {_p(pcap)} per period)" if pcap is not None else ""
        return (f"This Note is linked to {bw} of {joined}, {subj}, over {dur}. "
                f"At each {freq} reset date it pays {_p(rate)} of that period's rise{capph}; down periods pay "
                f"nothing and the strike resets. Capital is protected at {_p(min(prot, 1.0))} at maturity.")

    if lang == "es":
        subj = "los Subyacentes" if multi else "el Subyacente"
        bword = {"worst_of": "el peor rendimiento", "best_of": "el mejor rendimiento",
                 "average": "el rendimiento promedio"}.get(terms.participation_basket, "el rendimiento")
        head = (f"Esta Nota está vinculada a {bword} de {joined}, {subj}, con una duración máxima de {dur}. "
                f"No paga cupones periódicos; la redención al vencimiento depende del nivel final. ")
        if pd == "bear":
            body = (f"La Nota participa al {_p(rate)} de la caída por debajo del strike del {_p(strike)}, "
                    f"con un suelo del {_p(prot)}; por encima del strike el capital se redime al {_p(prot)}.")
            if cap is not None:
                body += f" La redención está limitada al {_p(1 + cap)}."
            return head + body
        if pu == "digital":
            up = (f"Si el nivel final está en o por encima del strike del {_p(strike)}, la Nota paga un importe fijo del {_p(1 + terms.digital_payout)}.")
        elif pu == "shark_fin":
            up = (f"Por encima del strike del {_p(strike)} se participa al {_p(rate)} de la subida hasta el knock-out del {_p(terms.knockout_level or 0)}; "
                  f"si el nivel final supera el knock-out, la Nota se redime al {_p(terms.knockout_payout)}.")
        else:
            up = f"Por encima del strike del {_p(strike)} se participa al {_p(rate)} de la subida"
            up += f", con un tope del {_p(1 + cap)}." if cap is not None else "."
        dn = {
            "full": f" Si el nivel final está por debajo del strike, el capital se redime al {_p(min(prot, 1.0))}.",
            "buffer": f" El capital está protegido hasta el nivel de protección del {_p(prot)}; por debajo, las pérdidas son 1:1.",
            "airbag": f" El capital está protegido hasta la barrera del {_p(prot)}; por debajo, la redención es apalancada (nivel final dividido por la barrera).",
        }.get(pd, "")
        return head + up + dn

    subj = "the Underlyings" if multi else "the Underlying"
    bword = {"worst_of": "the worst-performing", "best_of": "the best-performing",
             "average": "the average"}.get(terms.participation_basket, "the")
    head = (f"This Note is linked to {bword} of {joined}, {subj}, over a maximum term of {dur}. "
            f"It pays no periodic coupons; redemption at maturity depends on the final level. ")
    if pd == "bear":
        body = (f"The Note participates at {_p(rate)} of the fall below the {_p(strike)} strike, floored at {_p(prot)}; "
                f"above the strike capital is redeemed at {_p(prot)}.")
        if cap is not None:
            body += f" Redemption is capped at {_p(1 + cap)}."
        return head + body
    if pu == "digital":
        up = f"If the final level is at or above the {_p(strike)} strike, the Note pays a fixed {_p(1 + terms.digital_payout)}."
    elif pu == "shark_fin":
        up = (f"Above the {_p(strike)} strike you participate at {_p(rate)} of the rise up to the {_p(terms.knockout_level or 0)} knock-out; "
              f"if the final level is above the knock-out, the Note redeems at {_p(terms.knockout_payout)}.")
    else:
        up = f"Above the {_p(strike)} strike you participate at {_p(rate)} of the rise"
        up += f", capped at {_p(1 + cap)}." if cap is not None else "."
    dn = {
        "full": f" If the final level is below the strike, capital is redeemed at {_p(min(prot, 1.0))}.",
        "buffer": f" Capital is protected down to the {_p(prot)} protection level; below it, losses apply one-for-one.",
        "airbag": f" Capital is protected down to the {_p(prot)} barrier; below it, redemption is geared (final level divided by the barrier).",
    }.get(pd, "")
    return head + up + dn


def _basket_word(kind: str, lang: str, multi: bool) -> str:
    """How a basket rule reads in prose."""
    if not multi:
        return "el Subyacente" if lang == "es" else "the Underlying"
    if lang == "es":
        return {"worst_of": "el peor de los Subyacentes",
                "best_of": "el mejor de los Subyacentes",
                "average": "el promedio de los Subyacentes"}.get(kind, "el peor de los Subyacentes")
    return {"worst_of": "the worst-performing Underlying",
            "best_of": "the best-performing Underlying",
            "average": "the average of the Underlyings"}.get(kind, "the worst-performing Underlying")


def _phoenix_features(terms, lang: str, multi: bool) -> list[str]:
    """One short paragraph per ACTIVE feature: what the mechanic IS, then this
    note's numbers. Only features the note actually uses are described, so the
    prose never explains something the reader cannot see in the terms."""
    out: list[str] = []
    pct = _pct
    es = lang == "es"

    # ── basket rule ────────────────────────────────────────────────────────
    if multi:
        cb, ab = terms.coupon_basket, terms.autocall_basket
        cw, aw = _basket_word(cb, lang, True), _basket_word(ab, lang, True)
        if es:
            same = ("Cesta. Todas las condiciones se miden sobre "
                    f"{cw}: basta con que ese Subyacente incumpla un nivel para que la condición "
                    "no se cumpla, por muy bien que se comporten los demás.")
            diff = (f"Cesta. El cupón se mide sobre {cw} y la cancelación anticipada sobre {aw}.")
        else:
            same = ("Basket. Every condition is measured on "
                    f"{cw}: it only takes that one Underlying to miss a level for the condition to "
                    "fail, however well the others perform.")
            diff = (f"Basket. The coupon is measured on {cw}, while early redemption is measured on {aw}.")
        out.append(same if cb == ab else diff)

    # ── step-down autocall ─────────────────────────────────────────────────
    step = getattr(terms, "autocall_step_down", 0.0) or 0.0
    if step > 0:
        sched = terms.autocall_barrier_schedule()
        first, last = sched[terms.autocall_start_period - 1], sched[-1]
        floor = terms.autocall_floor
        if es:
            txt = ("Step-down (barrera decreciente). La barrera de cancelación anticipada no es fija: "
                   f"empieza en el {pct(first)} en la primera observación con posibilidad de cancelación y baja "
                   f"{pct(step)} en cada observación posterior")
            txt += f", con un suelo del {pct(floor)}." if floor is not None else "."
            txt += (f" Al final del plazo la Nota puede cancelarse con el Subyacente en el {pct(last)}, "
                    "de modo que cuanto más dura la Nota, más fácil le resulta cancelarse.")
        else:
            txt = ("Step-down (declining barrier). The early-redemption barrier is not fixed: it starts at "
                   f"{pct(first)} on the first callable observation and falls {pct(step)} at each observation "
                   "thereafter")
            txt += f", subject to a {pct(floor)} floor." if floor is not None else "."
            txt += (f" By the end of the term the Note can redeem with the Underlying at {pct(last)}, so the "
                    "longer the Note runs the easier it becomes for it to redeem.")
        out.append(txt)

    # ── premium paid only at redemption ────────────────────────────────────
    if getattr(terms, "coupon_at_autocall_only", False):
        out.append(
            "Prima a la cancelación. La Nota no paga cupones periódicos: la prima se acumula en cada "
            "observación y se abona en un único pago cuando la Nota se cancela anticipadamente o vence."
            if es else
            "Premium at redemption. The Note pays no periodic coupons: the premium accrues at each "
            "observation and is paid as a single lump sum when the Note redeems early or matures.")

    # ── One Star ───────────────────────────────────────────────────────────
    lvl = terms.one_star_level
    if lvl is not None and multi:
        acts_es, acts_en = [], []
        if terms.one_star_coupon:
            acts_es.append("pagar el cupón"); acts_en.append("pay the coupon")
        if terms.one_star_autocall:
            acts_es.append("activar la cancelación anticipada"); acts_en.append("trigger early redemption")
        if es:
            txt = ("One Star. Una excepción a la regla del peor de: en lugar de exigir que TODOS los "
                   f"Subyacentes cumplan, basta con que UNO SOLO esté en o por encima del {pct(lvl)} de su "
                   "nivel inicial. ")
            txt += (f"Ese único Subyacente basta para {' y '.join(acts_es)}, y para devolver el capital a la "
                    "par al vencimiento aunque el peor haya perforado la Barrera de Knock-in."
                    if acts_es else
                    "Se aplica únicamente a la redención final: devuelve el capital a la par al vencimiento "
                    "aunque el peor Subyacente haya perforado la Barrera de Knock-in, sin afectar al cupón "
                    "ni a la cancelación anticipada.")
        else:
            txt = ("One Star. An exception to the worst-of rule: instead of requiring EVERY Underlying to "
                   f"qualify, a SINGLE Underlying at or above {pct(lvl)} of its initial level is enough. ")
            txt += (f"That one Underlying suffices to {' and '.join(acts_en)}, and to repay capital at par at "
                    "maturity even if the worst has breached the Knock-in Barrier."
                    if acts_en else
                    "It applies to final redemption only: it repays capital at par at maturity even if the "
                    "worst Underlying has breached the Knock-in Barrier, without affecting the coupon or "
                    "early-redemption conditions.")
        out.append(txt)

    # ── Zenith ─────────────────────────────────────────────────────────────
    if getattr(terms, "zenith", False):
        rate = _pct(terms.participation_rate or 1.0)
        cap = terms.upside_cap
        wof = _basket_word("worst_of", lang, multi)
        if es:
            capw = "sin límite" if cap is None else f"limitada a +{_pct(cap)}"
            out.append(
                "Zenith. Convierte una Nota de ingresos en una que además participa de la subida. "
                "Siempre que la Nota se cancele anticipadamente, o venza con el Nivel Final en o por encima "
                f"de su nivel inicial, el inversor recibe —además del cupón y del capital— una participación "
                f"del {rate} en la revalorización de {wof} ({capw}). Si la Nota termina por debajo de la par, "
                "Zenith no aplica y rige la protección habitual.")
        else:
            capw = "uncapped" if cap is None else f"capped at +{_pct(cap)}"
            out.append(
                "Zenith. Turns an income Note into one that also participates in the upside. Whenever the "
                "Note redeems early, or matures with the Final Level at or above its initial level, the "
                f"investor receives — on top of the coupon and capital — {rate} participation in the rise of "
                f"{wof} ({capw}). If the Note finishes below par, Zenith does not apply and the usual "
                "protection governs.")

    # ── partial principal protection ───────────────────────────────────────
    pp = getattr(terms, "principal_protection", 1.0)
    if pp is not None and abs(pp - 1.0) > 1e-9:
        out.append(
            f"Protección del principal. Si la Nota llega a vencimiento sin haber perforado la Barrera de "
            f"Knock-in, el capital se redime al {pct(pp)} en lugar de la par."
            if es else
            f"Principal protection. If the Note reaches maturity without breaching the Knock-in Barrier, "
            f"capital redeems at {pct(pp)} rather than at par.")

    return out


def describe_note(terms, lang: str = "en") -> str:
    """Generate the prose note description from `terms` (en/es)."""
    names = list((terms.tickers or {}).values())
    multi = len(names) > 1
    if getattr(terms, "note_type", "") == "participation":
        return _describe_participation(terms, lang, names, multi)
    freq = _freq_word(terms.payment_freq, lang)
    dur = _fmt_duration(terms.maturity, lang)
    cpn = _pct(terms.coupon_pa)
    cb = _pct(terms.coupon_barrier)
    ki = _pct(terms.knock_in_barrier)
    start = max(1, int(terms.autocall_start_period))
    joined = _join_names(names, lang)
    os_lvl = terms.one_star_level

    if lang == "es":
        each = "cada Subyacente" if multi else "el Subyacente"
        anyu = "alguno de los Subyacentes" if multi else "el Subyacente"
        subj = "los Subyacentes" if multi else "el Subyacente"
        p = (
            f"Esta Inversión (la Nota) genera unos Ingresos con posibilidad de cancelación "
            f"anticipada y está vinculada al rendimiento de {joined}, {subj}. "
            f"Tiene una duración máxima de {dur} y genera un Ingreso equivalente al {cpn} p.a., "
            f"siempre y cuando el precio de cierre de {each} sea igual o superior al {cb} de su "
            f"nivel de Strike en cada observación {freq}. "
            f"Si el precio de cierre de {anyu} se encuentra por debajo del {cb} de su nivel de "
            f"Strike en cualquier Fecha de Observación {freq} el cupón de dicha observación {freq} "
            f"no es pagado. "
        )
        if terms.memory:
            p += (
                f"Sin embargo, los cupones no pagados pueden ser pagados en una futura observación "
                f"{freq} si el precio de cierre de {each} se encuentra por encima de la Barrera de "
                f"Cupón en la Fecha de Observación {freq} relevante (efecto memoria). "
            )
        p += (
            f"La Nota tiene también la posibilidad de vencer anticipadamente a partir de la "
            f"observación {start} y en cada Fecha de Observación {freq} en adelante, siempre y cuando "
            f"el precio de cierre de {each} sea igual o superior al nivel de Autocall de dicha Fecha "
            f"de Observación {freq}. "
        )
        p += (
            f"El Capital se encuentra en riesgo si la Nota no ha vencido anticipadamente y el Nivel "
            f"Final de {anyu} se encuentra por debajo del {ki} de su nivel de Strike inicial en la "
            f"Fecha de Observación Final."
        )
        return "\n\n".join([p] + _phoenix_features(terms, lang, multi))

        return p

    # English
    each = "each Underlying" if multi else "the Underlying"
    anyu = "any Underlying" if multi else "the Underlying"
    subj = "the Underlyings" if multi else "the Underlying"
    p = (
        f"This Investment (the Note) generates Income with the possibility of early redemption and is "
        f"linked to the performance of {joined}, {subj}. "
        f"It has a maximum duration of {dur} and pays Income equivalent to {cpn} p.a., provided that the "
        f"closing price of {each} is at or above {cb} of its Strike level on each {freq} observation. "
        f"If the closing price of {anyu} is below {cb} of its Strike level on any {freq} Observation "
        f"Date, the coupon for that {freq} observation is not paid. "
    )
    if terms.memory:
        p += (
            f"However, unpaid coupons may be paid on a future {freq} observation if the closing price of "
            f"{each} is above the Coupon Barrier on the relevant {freq} Observation Date (memory effect). "
        )
    p += (
        f"The Note may also redeem early from observation {start} and on each {freq} Observation Date "
        f"thereafter, provided that the closing price of {each} is at or above the Autocall level of that "
        f"{freq} Observation Date. "
    )
    p += (
        f"Capital is at risk if the Note has not redeemed early and the Final Level of {anyu} is below "
        f"{ki} of its initial Strike level on the Final Observation Date."
    )
    return "\n\n".join([p] + _phoenix_features(terms, lang, multi))
