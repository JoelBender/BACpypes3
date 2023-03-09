#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BitString
--------------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob, btox
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, BitString

# some debugging
_debug = 0
_log = ModuleLogger(globals())


class SampleBitString(BitString):
    b0 = 0
    b1 = 1
    b4 = 4


@bacpypes_debugging
def bit_string_tag(x):
    """Convert a hex string to an octet string application tag."""
    if _debug:
        bit_string_tag._debug("bit_string_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.bitString, len(b), b)
    if _debug:
        bit_string_tag._debug("    - tag: %r, %r", tag, btox(tag.tag_data))

    return tag


@bacpypes_debugging
def bit_string_encode(obj):
    """Encode a BitString object into a tag."""
    if _debug:
        bit_string_encode._debug("bit_string_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        bit_string_encode._debug("    - tag: %r, %r", tag, btox(tag.tag_data))

    return tag


@bacpypes_debugging
def bit_string_decode(tag):
    """Decode a BitString from a tag."""
    if _debug:
        bit_string_decode._debug("bit_string_decode %r", tag)

    obj = BitString.decode(TagList([tag]))
    if _debug:
        bit_string_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def bit_string_endec(v, x):
    """Pass the value to BitString, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        bit_string_endec._debug("bit_string_endec %r %r", v, x)

    obj = BitString(v)
    tag = bit_string_tag(x)

    assert bit_string_encode(obj) == tag
    assert bit_string_decode(tag) == obj


@bacpypes_debugging
class TestBitString(unittest.TestCase):
    def test_bit_string(self):
        if _debug:
            TestBitString._debug("test_bit_string")

        obj = BitString([])
        assert obj == []

        obj = BitString([0])
        assert obj == [0]

        obj = BitString([0, 1])
        assert obj == [0, 1]

        with pytest.raises(TypeError):
            BitString(1)
        with pytest.raises(ValueError):
            BitString("some bits")

    def test_bit_string_sample(self):
        if _debug:
            TestBitString._debug("test_bit_string_sample")

        obj = SampleBitString([])
        assert obj == [0] * 5

        obj = SampleBitString([0, 1, 4])
        assert obj == [1, 1, 0, 0, 1]

        obj = SampleBitString("0;1;4")
        assert obj == [1, 1, 0, 0, 1]

        obj = SampleBitString("b0;2")
        assert obj == [1, 0, 1, 0, 0]
        assert str(obj) == "b0;2"

    def test_bit_string_copy(self):
        if _debug:
            TestBitString._debug("test_bit_string_copy")

        obj1 = BitString([])
        obj2 = BitString(obj1)
        assert obj1 == obj2

    def test_bit_string_endec(self):
        if _debug:
            TestBitString._debug("test_bit_string_endec")

        # bit_string_endec([], '00')
        bit_string_endec([0], "0700")
        bit_string_endec([1], "0780")
        bit_string_endec([0] * 2, "0600")
        bit_string_endec([1] * 2, "06c0")
        bit_string_endec([0] * 10, "060000")
        bit_string_endec([1] * 10, "06ffc0")
