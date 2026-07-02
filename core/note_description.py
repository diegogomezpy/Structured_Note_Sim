"""Systematic, terms-driven note description — the "Esta Inversión (la Nota)…"
prose blurb that fills itself out from a note's terms.

Pure function of NoteTerms: no I/O, no Streamlit. Used by the PDF report and
exposed via the API. Bilingual (en/es). A TS mirror lives in
``web/src/lib/noteDescription.ts`` for the live web display — keep the two in
sync if the template changes.
"""
from __future__ import annotations


def _fmt_duration(maturity: float, lang: str) -> str:
    months = round(maturity * 12)
    if months % 12 == 0:
        y = months // 12
        if lang == "es":
            return f"{y} año" if y == 1 else f"{y} años"
        return f"{y} year" if y == 1 else f"{y} years"
    return f"{months} meses" if lang == "es" else f"{months} months"


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
    def _p(x):
        return f"{x * 100:.2f}".rstrip("0").rstrip(".") + "%"
    prot, rate = terms.protection_level or 0.0, terms.participation_rate or 0.0
    strike, cap = terms.participation_strike or 1.0, terms.upside_cap
    pd, pu = terms.participation_downside, terms.participation_upside

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


def describe_note(terms, lang: str = "en") -> str:
    """Generate the prose note description from `terms` (en/es)."""
    names = list((terms.tickers or {}).values())
    multi = len(names) > 1
    if getattr(terms, "note_type", "") == "participation":
        return _describe_participation(terms, lang, names, multi)
    freq = _freq_word(terms.payment_freq, lang)
    dur = _fmt_duration(terms.maturity, lang)
    cpn = f"{terms.coupon_pa:.2%}"
    cb = f"{terms.coupon_barrier:.2%}"
    ki = f"{terms.knock_in_barrier:.2%}"
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
        if os_lvl is not None:
            extra = []
            if terms.one_star_coupon:   extra.append("pagar el cupón")
            if terms.one_star_autocall: extra.append("activar la cancelación anticipada")
            lead = (f"Adicionalmente, bajo la característica One-Star, un único Subyacente en o por "
                    f"encima del {os_lvl:.2%} de su nivel de Strike ")
            if extra:
                acts = " y ".join(extra)
                p += (lead + f"basta por sí solo para {acts}, y para devolver el capital a la par en "
                      f"el vencimiento aunque el peor Subyacente haya perforado la Barrera de Knock-in. ")
            else:
                p += (lead + "permite devolver el capital a la par en el vencimiento aunque el peor "
                      "Subyacente haya perforado la Barrera de Knock-in (no afecta al cupón ni a la "
                      "cancelación anticipada). ")
        p += (
            f"El Capital se encuentra en riesgo si la Nota no ha vencido anticipadamente y el Nivel "
            f"Final de {anyu} se encuentra por debajo del {ki} de su nivel de Strike inicial en la "
            f"Fecha de Observación Final."
        )
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
    if os_lvl is not None:
        extra = []
        if terms.one_star_coupon:   extra.append("pay the coupon")
        if terms.one_star_autocall: extra.append("trigger early redemption")
        lead = (f"In addition, under the One-Star feature, a single Underlying at or above "
                f"{os_lvl:.2%} of its Strike level ")
        if extra:
            acts = " and ".join(extra)
            p += (lead + f"is enough on its own to {acts}, and to repay capital at par at maturity "
                  f"even if the worst Underlying has breached the Knock-in Barrier. ")
        else:
            p += (lead + "repays capital at par at maturity even if the worst Underlying has breached "
                  "the Knock-in Barrier (it does not affect the coupon or early-redemption conditions). ")
    p += (
        f"Capital is at risk if the Note has not redeemed early and the Final Level of {anyu} is below "
        f"{ki} of its initial Strike level on the Final Observation Date."
    )
    return p
