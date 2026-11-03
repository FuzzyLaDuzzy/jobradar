"""The salary a posting states, if it states one: "1.200€ - 1.500€", "€30K-40K", "30 000 € brutos/ano".

Only amounts in euros, and only plausible ones (a 9,60 € meal allowance is not a salary). A yearly amount is
also given per month, over 14 payments as is usual in Portugal, so the filter compares like with like.
"""

from __future__ import annotations

import re

_NUM = r"(\d{1,3}(?:[.,\s ]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d+)?)\s*([kK])?"
_EURO = r"(?:€|\beur\b|\beuros?\b)"
_PATTERNS = [
    # "1.200€ - 1.500€", "1200 a 1500 euros", "30k-40k €"
    re.compile(_NUM + r"\s*(?:" + _EURO + r")?\s*(?:-|–|a|to)\s*" + _NUM + r"\s*" + _EURO, re.I),
    # "€1,200 - €1,500", "€30K-40K"
    re.compile(_EURO + r"\s*" + _NUM + r"\s*(?:-|–|a|to)\s*" + _EURO + r"?\s*" + _NUM, re.I),
    re.compile(_NUM + r"\s*" + _EURO, re.I),  # "1.300 € brutos"
    re.compile(_EURO + r"\s*" + _NUM, re.I),  # "€ 1300"
]
_YEAR = re.compile(r"^.{0,25}?(/\s*ano|por ano|anua|ano\b|/\s*year|per year|a year|annual|p\.?\s?a\.)", re.I | re.S)
_MONTH = re.compile(r"^.{0,25}?(/\s*m[eê]s|por m[eê]s|mensa|/\s*month|per month|a month|monthly)", re.I | re.S)
_HOUR = re.compile(r"^\s*(/\s*h\b|/\s*hora|por hora|/\s*hour|per hour|an hour)", re.I)
MONTHS = 14  # payments a year in Portugal


def _number(digits: str, thousands: str) -> float:
    s = re.sub(r"[\s ]", "", digits)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d{1,2}", s):  # 1.200,50
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):  # 1.200 or 1,200
        s = re.sub(r"[.,]", "", s)
    else:  # 2,5 or 2.5
        s = s.replace(",", ".")
    value = float(s)
    return value * 1000 if thousands else value


def find(text: str) -> dict | None:
    """{"text": as written in the posting, "min"/"max": per month in euros, "period": "month" or "year"}, or None."""
    text = text or ""
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            values = [_number(groups[i], groups[i + 1]) for i in range(0, len(groups), 2)]
            after = text[match.end():match.end() + 40]
            if _HOUR.match(after):
                continue
            low, high = min(values), max(values)
            if _YEAR.match(after):
                period = "year"
            elif _MONTH.match(after):
                period = "month"
            else:  # nothing said: a "30k" or a five-digit amount is per year
                period = "year" if low >= 7000 else "month"
            per_month = 1 if period == "month" else MONTHS
            low, high = round(low / per_month), round(high / per_month)
            if not 500 <= low <= high <= 20000:  # not a salary: an allowance, a bonus, a price…
                continue
            words = re.match(r"\s*(?:brutos?|l[ií]quidos?|gross|net)?\s*(?:/\s*\w+|por \w+|per \w+)?", after)
            return {"text": (match.group(0) + (words.group(0) if words else "")).strip(),
                    "min": low, "max": high, "period": period}
    return None
