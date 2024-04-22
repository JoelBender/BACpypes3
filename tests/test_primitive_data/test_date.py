#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Date
---------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, Date
from bacpypes3.rdf.util import (
    date_encode as rdf_date_encode,
    date_decode as rdf_date_decode,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def date_tag(x):
    """Convert a hex string to a real application tag."""
    if _debug:
        date_tag._debug("date_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.date, len(b), b)
    if _debug:
        date_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def date_encode(obj):
    """Encode a Date object into a tag."""
    if _debug:
        date_encode._debug("date_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        date_encode._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def date_decode(tag):
    """Decode a Date from a tag."""
    if _debug:
        date_decode._debug("date_decode %r", tag)

    obj = Date.decode(TagList([tag]))
    if _debug:
        date_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def date_endec(v, x):
    """Pass the value to Date, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        date_endec._debug("date_endec %r %r", v, x)

    obj = Date(v)
    if _debug:
        date_endec._debug("    - obj: %r", obj)

    tag = date_tag(x)
    if _debug:
        date_endec._debug("    - tag: %r", tag)
        tag.debug_contents()

    assert date_encode(obj) == tag
    assert date_decode(tag) == obj


@bacpypes_debugging
class TestDate(unittest.TestCase):
    def test_date_error(self):
        if _debug:
            TestDate._debug("test_date_error")

        with pytest.raises(TypeError):
            Date(1.5)
        with pytest.raises(ValueError):
            Date("some string")

    def test_date_tuple(self):
        if _debug:
            TestDate._debug("test_date_tuple")

        obj = Date((1, 2, 3, 4))
        assert obj == (1, 2, 3, 4)
        assert str(obj) == "1901-2-3 thu"

        obj = Date((2001, 3, 4, 5))
        assert obj == (101, 3, 4, 5)
        assert str(obj) == "2001-3-4 fri"

    def test_date_string(self):
        if _debug:
            TestDate._debug("test_date_string")

        # calulate DOW
        obj = Date("1901-2-3")
        assert obj == (1, 2, 3, 7)
        assert str(obj) == "1901-2-3 sun"

        # provide a wrong DOW, but accept it
        obj = Date("1901-2-3 thu")
        assert obj == (1, 2, 3, 4)
        assert str(obj) == "1901-2-3 thu"

        # specific date, explicit wildcard DOW
        obj = Date("1901-2-3 *")
        assert obj == (1, 2, 3, 255)

        # any day in 1901, implicit wildcard DOW
        obj = Date("1901-*-*")
        assert obj == (1, 255, 255, 255)
        assert str(obj) == "1901-*-* *"

        # any Monday in 1901
        obj = Date("1901-*-* mon")
        assert obj == (1, 255, 255, 1)
        assert str(obj) == "1901-*-* mon"

    def test_date_copy(self):
        if _debug:
            TestDate._debug("test_date_copy")

        obj1 = Date((5, 6, 7, 8))
        obj2 = Date(obj1)
        assert obj1 == obj2

    def test_date_endec(self):
        if _debug:
            TestDate._debug("test_date_endec")

        date_endec((1, 2, 3, 4), "01020304")

    def test_date_isoformat(self):
        if _debug:
            TestDate._debug("test_date_isoformat")

        obj1 = Date("1901-2-3")
        obj1_string = obj1.isoformat()
        if _debug:
            TestDate._debug("    - obj1_string: %r", obj1_string)

        obj2 = Date.fromisoformat(obj1_string)
        assert obj1 == obj2

    def test_time_literal(self):
        if _debug:
            TestDate._debug("test_time_literal")

        # specific date
        obj1 = Date("1901-2-3")
        obj1_literal = rdf_date_encode(None, obj1)
        if _debug:
            TestDate._debug("    - obj1_literal: %r", obj1_literal)

        obj2 = rdf_date_decode(None, obj1_literal)
        assert obj1 == obj2

        # date pattern
        obj3 = Date("1901-*-*")
        obj3_literal = rdf_date_encode(None, obj3)
        if _debug:
            TestDate._debug("    - obj3_literal: %r", obj3_literal)

        obj4 = rdf_date_decode(None, obj3_literal)
        assert obj3 == obj4
