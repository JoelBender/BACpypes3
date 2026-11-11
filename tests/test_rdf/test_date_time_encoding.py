#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test RDF Date, Time and ObjectIdentifier Encoding
-------------------------------------------------

The values are strings matching the csml2rdf bacnet.ttl shapes.
"""

import re

import pytest
from rdflib import Graph, Literal  # type: ignore[import]
from rdflib.namespace import XSD  # type: ignore[import]

from bacpypes3.primitivedata import Date, Time, ObjectIdentifier
from bacpypes3.rdf.core import BACNET
from bacpypes3.rdf.util import (
    date_encode,
    date_decode,
    time_encode,
    time_decode,
    objectidentifier_encode,
    objectidentifier_decode,
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
