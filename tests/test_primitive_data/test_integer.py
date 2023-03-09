#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Integer
------------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, Integer

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def integer_tag(x):
    """Convert a hex string to an integer application tag."""
    if _debug:
        integer_tag._debug("integer_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.integer, len(b), b)
    if _debug:
        integer_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def integer_encode(obj):
    """Encode a Integer object into a tag."""
    if _debug:
        integer_encode._debug("integer_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        integer_encode._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def integer_decode(tag):
    """Decode a null from a tag."""
    if _debug:
        integer_decode._debug("integer_decode %r", tag)

    obj = Integer.decode(TagList([tag]))
    if _debug:
        integer_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def integer_endec(v, x):
    """Pass the value to Integer, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        integer_endec._debug("integer_endec %r %r", v, x)

    obj = Integer(v)
    if _debug:
        integer_endec._debug("    - obj: %r", obj)

    tag = integer_tag(x)
    if _debug:
        integer_endec._debug("    - tag: %r", tag)

    assert integer_encode(obj) == tag
    assert integer_decode(tag) == obj


@bacpypes_debugging
class TestInteger(unittest.TestCase):
    def test_integer(self):
        if _debug:
            TestInteger._debug("test_integer")

        obj = Integer(0)
        assert obj == 0

        with pytest.raises(ValueError):
            Integer("some string")
        with pytest.raises(TypeError):
            Integer(1.0)

    def test_integer_value(self):
        if _debug:
            TestInteger._debug("test_integer_value")

        obj = Integer(1)
        assert obj == 1

    def test_integer_copy(self):
        if _debug:
            TestInteger._debug("test_integer_copy")

        obj1 = Integer(2)
        obj2 = Integer(obj1)
        assert obj1 == obj2

    def test_integer_endec(self):
        if _debug:
            TestInteger._debug("test_integer_endec")

        integer_endec(0, "00")
        integer_endec(1, "01")
        integer_endec(127, "7F")
        integer_endec(-1, "FF")
