#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test RDF Date, Time, WeekNDay and ObjectIdentifier Encoding
-----------------------------------------------------------

The values are strings matching the csml2rdf bacnet.ttl shapes.
"""

import re

import pytest
from rdflib import Graph, Literal  # type: ignore[import]
from rdflib.namespace import XSD  # type: ignore[import]

from bacpypes3.basetypes import CalendarEntry, DateTime, DateTimePattern, WeekNDay
from bacpypes3.primitivedata import (
    Date,
    DatePattern,
    Time,
    TimePattern,
    ObjectIdentifier,
)
from bacpypes3.rdf.core import BACNET
from bacpypes3.rdf.util import (
    atomic_decode,
    atomic_encode,
    datetime_decode,
    datetime_encode,
    date_encode,
    date_decode,
    time_encode,
    time_decode,
    objectidentifier_encode,
    objectidentifier_decode,
    weeknday_decode,
    weeknday_encode,
)

# patterns from csml2rdf bacnet.ttl
LOCAL_DATE_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2}|[*])( ([0-9]|[*]))?$")
DATE_PATTERN_RE = re.compile(
    r"^([0-9]{4}|[*])-([0-9]{2}|[*])-([0-9]{2}|[*])( ([0-9]|[*]))?$"
)
LOCAL_TIME_RE = re.compile(r"^([0-9]{2}):([0-9]{2}):([0-9]{2})[.]([0-9]{2})$")
TIME_PATTERN_RE = re.compile(
    r"^([0-9]{2}|[*]):([0-9]{2}|[*]):([0-9]{2}|[*])[.]([0-9]{2}|[*])$"
)
OBJECT_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9-]+,[1-9][0-9]*$")
WEEKNDAY_RE = re.compile(r"^([1-9][0-9]*|[*]),([1-9][0-9]*|[*]),([1-9][0-9]*|[*])$")


def test_local_date():
    literal = date_encode(Graph(), Date("2026-11-10"))
    assert literal == Literal("2026-11-10 2")
    assert literal.datatype is None
    assert LOCAL_DATE_RE.match(str(literal))
    assert date_decode(Graph(), literal) == Date("2026-11-10")


@pytest.mark.parametrize(
    "value,expected",
    [
        ((126, 11, 255, 255), "2026-11-* *"),
        ((255, 255, 255, 255), "*-*-* *"),
        ((255, 1, 1, 255), "*-01-01 *"),
    ],
)
def test_date_pattern(value, expected):
    literal = date_encode(Graph(), Date(value))
    assert str(literal) == expected
    assert DATE_PATTERN_RE.match(expected)
    assert tuple(date_decode(Graph(), literal)) == value


def test_date_without_day_of_week():
    assert date_decode(Graph(), Literal("2026-11-10")) == Date("2026-11-10")


def test_local_time():
    literal = time_encode(Graph(), Time("1:02:03.40"))
    assert literal == Literal("01:02:03.40")
    assert LOCAL_TIME_RE.match(str(literal))
    assert time_decode(Graph(), literal) == Time("1:02:03.40")


def test_time_pattern():
    literal = time_encode(Graph(), Time((255, 255, 255, 255)))
    assert str(literal) == "*:*:*.*"
    assert TIME_PATTERN_RE.match(str(literal))
    assert tuple(time_decode(Graph(), literal)) == (255, 255, 255, 255)


def test_legacy_typed_literals_still_decode():
    assert date_decode(Graph(), Literal("2026-11-10", datatype=XSD.date)) == Date(
        "2026-11-10"
    )
    assert time_decode(Graph(), Literal("12:34:56", datatype=XSD.time)) == Time(
        "12:34:56"
    )
    assert objectidentifier_decode(
        Graph(), Literal("analog-input,1", datatype=BACNET.objectIdentifier)
    ) == ObjectIdentifier("analog-input,1")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("analog-input,1", "analog-input,1"),
        ("analog-input,0", "analog-input,0"),
        ((128, 5), "128,5"),
    ],
)
def test_object_identifier(value, expected):
    literal = objectidentifier_encode(Graph(), ObjectIdentifier(value))
    assert literal == Literal(expected)
    assert objectidentifier_decode(Graph(), literal) == ObjectIdentifier(value)


def test_object_identifier_pattern():
    assert OBJECT_IDENTIFIER_RE.match("analog-input,1")
    # the shape pattern itself does not allow instance 0
    assert not OBJECT_IDENTIFIER_RE.match("analog-input,0")


#
#   Patterns are always typed, Date, Time and DateTime are not, and the
#   decoders accept any of the forms for either one
#

XMAS = (255, 12, 25, 255)


@pytest.mark.parametrize(
    "value,expected",
    [
        (XMAS, "*-12-25 *"),
        ((126, 11, 10, 2), "2026-11-10 2"),
        ((255, 255, 255, 255), "*-*-* *"),
    ],
)
def test_date_pattern_typed(value, expected):
    literal = date_encode(Graph(), DatePattern(value))
    assert literal == Literal(expected, datatype=BACNET.datePattern)
    assert DATE_PATTERN_RE.match(expected)

    result = date_decode(Graph(), literal, DatePattern)
    assert type(result) is DatePattern
    assert result == value

    # the same value as a Date is not typed
    assert date_encode(Graph(), Date(value)).datatype is None


@pytest.mark.parametrize(
    "literal",
    [
        Literal("*-12-25 *"),
        Literal("*-12-25 *", datatype=BACNET.datePattern),
        Literal("*-12-25", datatype=XSD.string),
    ],
)
def test_date_decode_generous(literal):
    for class_ in (Date, DatePattern):
        result = date_decode(Graph(), literal, class_)
        assert type(result) is class_
        assert result == XMAS

    # specific dates in any form
    for literal in (
        Literal("2026-11-10 2", datatype=BACNET.datePattern),
        Literal("2026-11-10", datatype=XSD.date),
        Literal("2026-11-10 tue", datatype=BACNET.datePattern),
    ):
        assert date_decode(Graph(), literal, DatePattern) == (126, 11, 10, 2)


def test_time_pattern_typed():
    literal = time_encode(Graph(), TimePattern("12:*"))
    assert literal == Literal("12:*:*.*", datatype=BACNET.timePattern)
    assert TIME_PATTERN_RE.match(str(literal))

    for literal in (
        literal,
        Literal("12:*:*.*"),
        Literal("12:00:00", datatype=XSD.time),
    ):
        for class_ in (Time, TimePattern):
            result = time_decode(Graph(), literal, class_)
            assert type(result) is class_

    assert time_encode(Graph(), Time("12:*")).datatype is None


def test_datetime_pattern_typed():
    value = DateTimePattern(date=XMAS, time=(12, 0, 0, 0))
    literal = datetime_encode(Graph(), value)
    assert literal == Literal("*-12-25 * 12:00:00.00", datatype=BACNET.dateTimePattern)

    # a wildcard year decodes, the Date string parser finds that ambiguous
    result = datetime_decode(Graph(), literal, DateTimePattern)
    assert type(result) is DateTimePattern
    assert result.date == XMAS
    assert result.time == (12, 0, 0, 0)

    # a specific datetime pattern is still typed
    literal = datetime_encode(Graph(), DateTimePattern("2026-11-10 12:00"))
    assert literal == Literal(
        "2026-11-10 2 12:00:00.00", datatype=BACNET.dateTimePattern
    )

    # DateTime is unchanged, and the pattern forms decode as a DateTime too
    assert (
        datetime_encode(Graph(), DateTime("2026-11-10 12:00")).datatype == XSD.dateTime
    )
    result = datetime_decode(Graph(), literal, DateTime)
    assert type(result) is DateTime
    assert result.date == (126, 11, 10, 2)
    result = datetime_decode(
        Graph(), Literal("2026-11-10T12:00:00", datatype=XSD.dateTime), DateTimePattern
    )
    assert type(result) is DateTimePattern


def test_atomic_dispatch():
    graph = Graph()
    for value, datatype in (
        (DatePattern(XMAS), BACNET.datePattern),
        (TimePattern("12:*"), BACNET.timePattern),
        (DateTimePattern(date=XMAS, time=(12, 0, 0, 0)), BACNET.dateTimePattern),
    ):
        literal = atomic_encode(graph, value)
        assert literal.datatype == datatype
        result = atomic_decode(graph, literal, type(value))
        assert type(result) is type(value)


#
#   WeekNDay is the month, week of month and day of week
#


@pytest.mark.parametrize(
    "value,expected",
    [
        (b"\x0c\xff\x07", "12,*,7"),  # every Sunday in December
        (b"\x0d\x01\x01", "13,1,1"),  # first Monday of odd months
        (b"\xff\xff\x05", "*,*,5"),  # every Friday
        (b"\xff\xff\xff", "*,*,*"),
    ],
)
def test_weeknday(value, expected):
    literal = weeknday_encode(Graph(), WeekNDay(value))
    assert literal == Literal(expected, datatype=BACNET.weekNDay)
    assert WEEKNDAY_RE.match(expected)

    result = weeknday_decode(Graph(), literal)
    assert type(result) is WeekNDay
    assert result == value


def test_weeknday_decode_generous():
    for literal in (
        Literal("12,*,7"),
        Literal("12,*,7", datatype=XSD.string),
        Literal("0cff07", datatype=XSD.hexBinary),
    ):
        assert weeknday_decode(Graph(), literal) == b"\x0c\xff\x07"

    with pytest.raises(ValueError):
        weeknday_decode(Graph(), Literal("12,7", datatype=BACNET.weekNDay))


def test_weeknday_atomic_dispatch():
    """WeekNDay is an OctetString but is not encoded as one."""
    element = CalendarEntry._elements["weeknday"]
    literal = atomic_encode(Graph(), element(b"\x0c\xff\x07"))
    assert literal == Literal("12,*,7", datatype=BACNET.weekNDay)
    result = atomic_decode(Graph(), literal, element)
    assert isinstance(result, WeekNDay)
    assert result == b"\x0c\xff\x07"
