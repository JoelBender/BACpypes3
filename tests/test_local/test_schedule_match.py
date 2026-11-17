"""
Test Schedule Date Range Matching
---------------------------------

Both ends of a BACnetDateRange are inclusive and an unspecified field takes
its value from the date being matched.  So "*-*-* *" .. "*-*-* *" is from the
beginning of time to the end of time, "*-*-* *" .. "2026-11-15" is true until
after the 15th, and "*-06-01 *" .. "*-08-31 *" is from the first of June to the
end of August of the same year, every year.
"""

from __future__ import annotations

import pytest

from bacpypes3.basetypes import CalendarEntry, DateRange
from bacpypes3.debugging import ModuleLogger
from bacpypes3.local.schedule import date_in_calendar_entry, match_date_range
from bacpypes3.primitivedata import Date, DatePattern

# some debugging
_debug = 0
_log = ModuleLogger(globals())

ANY = "*-*-* *"


def date_range(start: str, end: str) -> DateRange:
    return DateRange(startDate=DatePattern(start), endDate=DatePattern(end))


@pytest.mark.parametrize(
    "date, start, end, expected",
    [
        # from the beginning of time to the end of time
        ("1901-01-01", ANY, ANY, True),
        ("2026-11-15", ANY, ANY, True),
        ("2154-12-31", ANY, ANY, True),
        # open start, inclusive end
        ("1901-01-01", ANY, "2026-11-15", True),
        ("2026-11-15", ANY, "2026-11-15", True),
        ("2026-11-16", ANY, "2026-11-15", False),
        # inclusive start, open end
        ("2026-11-14", "2026-11-15", ANY, False),
        ("2026-11-15", "2026-11-15", ANY, True),
        ("2154-12-31", "2026-11-15", ANY, True),
        # both ends specific and inclusive
        ("2025-12-31", "2026-01-01", "2026-12-31", False),
        ("2026-01-01", "2026-01-01", "2026-12-31", True),
        ("2026-11-15", "2026-01-01", "2026-12-31", True),
        ("2026-12-31", "2026-01-01", "2026-12-31", True),
        ("2027-01-01", "2026-01-01", "2026-12-31", False),
        # every year, the first of June to the end of August of the same year
        ("2026-05-31", "*-06-01 *", "*-08-31 *", False),
        ("2026-06-01", "*-06-01 *", "*-08-31 *", True),
        ("2026-07-04", "*-06-01 *", "*-08-31 *", True),
        ("2026-08-31", "*-06-01 *", "*-08-31 *", True),
        ("2026-09-01", "*-06-01 *", "*-08-31 *", False),
        ("1999-07-04", "*-06-01 *", "*-08-31 *", True),
        ("2154-08-31", "*-06-01 *", "*-08-31 *", True),
        # a range does not wrap into the next year
        ("2026-12-15", "*-11-01 *", "*-02-28 *", False),
        ("2027-01-15", "*-11-01 *", "*-02-28 *", False),
        # every year from the first of June, until a specific end date
        ("2026-05-31", "*-06-01 *", "2027-08-31", False),
        ("2026-06-01", "*-06-01 *", "2027-08-31", True),
        ("2027-08-31", "*-06-01 *", "2027-08-31", True),
        ("2027-09-01", "*-06-01 *", "2027-08-31", False),
    ],
)
def test_match_date_range(date, start, end, expected):
    assert match_date_range(Date(date), date_range(start, end)) is expected


def test_calendar_entry_date_range():
    # calendar entries with a date range use the same matching
    entry = CalendarEntry(dateRange=date_range(ANY, "2026-11-15"))
    assert date_in_calendar_entry(Date("2026-11-15"), entry)
    assert not date_in_calendar_entry(Date("2026-11-16"), entry)

    entry = CalendarEntry(dateRange=date_range("*-06-01 *", "*-08-31 *"))
    assert date_in_calendar_entry(Date("2030-06-01"), entry)
    assert not date_in_calendar_entry(Date("2030-09-01"), entry)
