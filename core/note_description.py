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


def describe_note(terms, lang: str = "en") -> str:
    """Generate the prose note description from `terms` (en/es)."""
    names = list((terms.tickers or {}).values())
    multi = len(names) > 1
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
            p += (
                f"Adicionalmente, bajo la característica One-Star, un único Subyacente en o por encima "
                f"del {os_lvl:.2%} de su nivel de Strike basta por sí solo para satisfacer las "
                f"condiciones de cupón, cancelación anticipada y devolución de capital. "
            )
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
        p += (
            f"In addition, under the One-Star feature, a single Underlying at or above {os_lvl:.2%} of its "
            f"Strike level on its own satisfies the coupon, early-redemption and capital-repayment "
            f"conditions. "
        )
    p += (
        f"Capital is at risk if the Note has not redeemed early and the Final Level of {anyu} is below "
        f"{ki} of its initial Strike level on the Final Observation Date."
    )
    return p
