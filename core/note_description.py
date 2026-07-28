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
                body += f" La redención está limitada al {_p(1 + rate * cap)}."
            return head + body
        if pu == "digital":
            up = (f"Si el nivel final está en o por encima del strike del {_p(strike)}, la Nota paga un importe fijo del {_p(1 + terms.digital_payout)}.")
        elif pu == "shark_fin":
            up = (f"Por encima del strike del {_p(strike)} se participa al {_p(rate)} de la subida hasta el knock-out del {_p(terms.knockout_level or 0)}; "
                  f"si el nivel final supera el knock-out, la Nota se redime al {_p(terms.knockout_payout)}.")
        else:
            up = f"Por encima del strike del {_p(strike)} se participa al {_p(rate)} de la subida"
            up += f", con un tope del {_p(1 + rate * cap)}." if cap is not None else "."
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
            body += f" Redemption is capped at {_p(1 + rate * cap)}."
        return head + body
    if pu == "digital":
        up = f"If the final level is at or above the {_p(strike)} strike, the Note pays a fixed {_p(1 + terms.digital_payout)}."
    elif pu == "shark_fin":
        up = (f"Above the {_p(strike)} strike you participate at {_p(rate)} of the rise up to the {_p(terms.knockout_level or 0)} knock-out; "
              f"if the final level is above the knock-out, the Note redeems at {_p(terms.knockout_payout)}.")
    else:
        up = f"Above the {_p(strike)} strike you participate at {_p(rate)} of the rise"
        up += f", capped at {_p(1 + rate * cap)}." if cap is not None else "."
    dn = {
        "full": f" If the final level is below the strike, capital is redeemed at {_p(min(prot, 1.0))}.",
        "buffer": f" Capital is protected down to the {_p(prot)} protection level; below it, losses apply one-for-one.",
        "airbag": f" Capital is protected down to the {_p(prot)} barrier; below it, redemption is geared (final level divided by the barrier).",
    }.get(pd, "")
    return head + up + dn


def describe_note(terms, lang: str = "en", issuer: str | None = None) -> str:
    """Generate the prose note description from `terms` (en/es).

    Phoenix notes get the six-paragraph scheme in `core/phoenix_prose.py`;
    participation notes keep their own single-paragraph payoff profile.

    Routing mirrors `price_note` exactly (core/note.py): a positive
    `capital_guarantee` routes to the participation payoff regardless of
    `note_type`, so the prose must follow or a note is described as one thing
    and priced as another.
    """
    from core.phoenix_prose import describe_phoenix

    names = list((terms.tickers or {}).values())
    multi = len(names) > 1
    cg = getattr(terms, "capital_guarantee", None)
    if getattr(terms, "note_type", "") == "participation" or (cg is not None and cg > 0):
        return _describe_participation(terms, lang, names, multi)
    # A Phoenix with no observation schedule has nothing to describe — every
    # sentence in the prose is about what happens ON an observation date, and
    # the generators index the schedule directly (`c.ac[c.start - 1]`), so a
    # zero-observation note raised IndexError and took the whole report with it.
    if getattr(terms, "n_obs", 0) < 1:
        return ""
    return describe_phoenix(terms, lang, issuer)
