#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Unsigned
-------------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.primitivedata import (
    Tag,
    TagClass,
    TagNumber,
    TagList,
    Unsigned,
    Unsigned8,
    Unsigned16,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def unsigned_tag(x):
    """Convert a hex string to an integer application tag."""
    if _debug:
        unsigned_tag._debug("unsigned_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.unsigned, len(b), b)
    if _debug:
        unsigned_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def unsigned_encode(obj):
    """Encode a Unsigned object into a tag."""
    if _debug:
        unsigned_encode._debug("unsigned_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        unsigned_encode._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def unsigned_decode(tag):
    """Decode a null from a tag."""
    if _debug:
        unsigned_decode._debug("unsigned_decode %r", tag)

    obj = Unsigned.decode(TagList([tag]))
    if _debug:
        unsigned_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def unsigned_endec(v, x):
    """Pass the value to Unsigned, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        unsigned_endec._debug("unsigned_endec %r %r", v, x)

    obj = Unsigned(v)
    if _debug:
        unsigned_endec._debug("    - obj: %r", obj)

    tag = unsigned_tag(x)
    if _debug:
        unsigned_endec._debug("    - tag: %r", tag)

    assert unsigned_encode(obj) == tag
    assert unsigned_decode(tag) == obj


@bacpypes_debugging
class TestUnsigned(unittest.TestCase):
    def test_unsigned(self):
        if _debug:
            TestUnsigned._debug("test_unsigned")

        obj = Unsigned(0)
        assert obj == 0

        obj = Unsigned(1)
        assert obj == 1

        obj = Unsigned("2")
        assert obj == 2

        with pytest.raises(ValueError):
            Unsigned("some string")
        with pytest.raises(TypeError):
            Unsigned(1.0)

    def test_unsigned_value(self):
        if _debug:
            TestUnsigned._debug("test_unsigned_value")

        obj = Unsigned(1)
        assert obj == 1

    def test_unsigned_copy(self):
        if _debug:
            TestUnsigned._debug("test_unsigned_copy")

        obj1 = Unsigned(3)
        obj2 = Unsigned(obj1)
        assert obj1 == obj2

    def test_unsigned_endec(self):
        if _debug:
            TestUnsigned._debug("test_unsigned_endec")

        unsigned_endec(0, "00")
        unsigned_endec(1, "01")
        unsigned_endec(127, "7F")
        unsigned_endec(255, "FF")


@bacpypes_debugging
class TestUnsigned8(unittest.TestCase):
    def test_unsigned8(self):
        if _debug:
            TestUnsigned8._debug("test_unsigned8")

        with pytest.raises(ValueError):
            Unsigned8("some string")
        with pytest.raises(TypeError):
            Unsigned8(1.0)

        with pytest.raises(ValueError):
            Unsigned8(-1)
        with pytest.raises(ValueError):
            Unsigned8(256)


@bacpypes_debugging
class TestUnsigned16(unittest.TestCase):
    def test_unsigned16(self):
        if _debug:
            TestUnsigned16._debug("test_unsigned16")

        with pytest.raises(ValueError):
            Unsigned16(-1)
        with pytest.raises(ValueError):
            Unsigned16(65536)
