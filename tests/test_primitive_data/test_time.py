#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Time
---------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, Time
from bacpypes3.rdf.util import (
    time_encode as rdf_time_encode,
    time_decode as rdf_time_decode,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def time_tag(x):
    """Convert a hex string to a real application tag."""
    if _debug:
        time_tag._debug("time_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.time, len(b), b)
    if _debug:
        time_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def time_encode(obj):
    """Encode a Time object into a tag."""
    if _debug:
        time_encode._debug("time_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        time_encode._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def time_decode(tag):
    """Decode a Time from a tag."""
    if _debug:
        time_decode._debug("time_decode %r", tag)

    obj = Time.decode(TagList([tag]))
    if _debug:
        time_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def time_endec(v, x):
    """Pass the value to Time, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        time_endec._debug("time_endec %r %r", v, x)

    obj = Time(v)
    if _debug:
        time_endec._debug("    - obj: %r", obj)

    tag = time_tag(x)
    if _debug:
        time_endec._debug("    - tag: %r", tag)
        tag.debug_contents()

    assert time_encode(obj) == tag
    assert time_decode(tag) == obj


@bacpypes_debugging
class TestTime(unittest.TestCase):
    def test_time(self):
        if _debug:
            TestTime._debug("test_time")

        obj = Time((255, 255, 255, 255))
        assert obj == (255, 255, 255, 255)

        with pytest.raises(TypeError):
            Time(1.5)
        with pytest.raises(ValueError):
            Time("some string")

    def test_time_tuple(self):
        if _debug:
            TestTime._debug("test_time_tuple")

        obj = Time((1, 2, 3, 4))
        assert obj == (1, 2, 3, 4)
        assert str(obj) == "01:02:03.04"

    def test_time_copy(self):
        if _debug:
            TestTime._debug("test_time_copy")

        obj1 = Time((5, 6, 7, 8))
        obj2 = Time(obj1)
        assert obj1 == obj2

    def test_time_endec(self):
        if _debug:
            TestTime._debug("test_time_endec")

        time_endec((1, 2, 3, 4), "01020304")

    def test_time_isoformat(self):
        if _debug:
            TestTime._debug("test_time_isoformat")

        obj1 = Time("01:02:03.04")
        obj1_string = obj1.isoformat()
        if _debug:
            TestTime._debug("    - obj1_string: %r", obj1_string)

        obj2 = Time.fromisoformat(obj1_string)
        assert obj1 == obj2

    def test_time_literal(self):
        if _debug:
            TestTime._debug("test_time_literal")

        # specific time
        obj1 = Time("01:02:03.04")
        obj1_literal = rdf_time_encode(None, obj1)
        if _debug:
            TestTime._debug("    - obj1_literal: %r", obj1_literal)

        obj2 = rdf_time_decode(None, obj1_literal)
        assert obj1 == obj2

        # time pattern
        obj3 = Time("01:02:*")
        obj3_literal = rdf_time_encode(None, obj3)
        if _debug:
            TestTime._debug("    - obj3_literal: %r", obj3_literal)

        obj4 = rdf_time_decode(None, obj3_literal)
        assert obj3 == obj4
