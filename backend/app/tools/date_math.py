"""
Deterministic calendar maths (age, birthdays). Pure functions, no I/O, no clock access:
callers pass `today` explicitly so results are reproducible and testable.

Leap-day birthdays (29 February): in a non-leap year the birthday is counted
from 1 March, i.e. the person has not yet had it on 28 February.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime

_FORMATS = ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%Y/%m/%d")


def parse_date(text: str) -> date | None:
    """Parse an ISO date or a spelled-out one ('19 May 2007', 'May 19, 2007'); None if unrecognised."""
    cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", (text or "").strip().strip(".,"), flags=re.I)
    cleaned = re.sub(r"\bof\b", " ", re.sub(r"^the\s+", "", cleaned, flags=re.I), flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned)
    for fmt in _FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _anniversary(birth: date, year: int) -> date:
    """The birthday in `year` (1 March for a 29 February birthday in a non-leap year)."""
    if birth.month == 2 and birth.day == 29 and not calendar.isleap(year):
        return date(year, 3, 1)
    return date(year, birth.month, birth.day)


def calculate_age(birth: date, today: date) -> dict:
    """Exact age on `today`: whole years, plus months/days since the last birthday."""
    if birth > today:
        raise ValueError("The date of birth is in the future.")

    years = today.year - birth.year
    if today < _anniversary(birth, today.year):
        years -= 1
    last_birthday = _anniversary(birth, birth.year + years)

    months = (today.year - last_birthday.year) * 12 + today.month - last_birthday.month
    if today.day < last_birthday.day:
        months -= 1
    anchor_month_index = last_birthday.year * 12 + last_birthday.month - 1 + months
    anchor_year, anchor_month = divmod(anchor_month_index, 12)
    anchor_month += 1
    anchor = date(anchor_year, anchor_month, min(last_birthday.day, calendar.monthrange(anchor_year, anchor_month)[1]))
    days = (today - anchor).days

    next_birthday = _anniversary(birth, today.year)
    if next_birthday < today:
        next_birthday = _anniversary(birth, today.year + 1)

    return {
        "birth_date": birth.isoformat(),
        "as_of": today.isoformat(),
        "years": years,
        "months": months,
        "days": days,
        "birthday_today": next_birthday == today,
        "next_birthday": next_birthday.isoformat(),
        "days_until_next_birthday": (next_birthday - today).days,
    }
