#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Enumerated
---------------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob, btox
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, Enumerated

# some debugging
_debug = 0
_log = ModuleLogger(globals())


class QuickBrownFox(Enumerated):
    quick = 0
    brown = 1
    fox = 2


@bacpypes_debugging
def enumerated_tag(x):
    """Convert a hex string to an octet string application tag."""
    if _debug:
        enumerated_tag._debug("enumerated_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.enumerated, len(b), b)
    if _debug:
        enumerated_tag._debug("    - tag: %r, %r", tag, btox(tag.tag_data))

    return tag


@bacpypes_debugging
def enumerated_encode(obj):
    """Encode a Enumerated object into a tag."""
    if _debug:
        enumerated_encode._debug("enumerated_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        enumerated_encode._debug("    - tag: %r, %r", tag, btox(tag.tag_data))

    return tag


@bacpypes_debugging
def enumerated_decode(tag):
    """Decode a Enumerated from a tag."""
    if _debug:
        enumerated_decode._debug("enumerated_decode %r", tag)

    obj = Enumerated.decode(TagList([tag]))
    if _debug:
        enumerated_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def enumerated_endec(v, x):
    """Pass the value to Enumerated, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        enumerated_endec._debug("enumerated_endec %r %r", v, x)

    obj = Enumerated(v)
    tag = enumerated_tag(x)

    assert enumerated_encode(obj) == tag
    assert enumerated_decode(tag) == obj


@bacpypes_debugging
class TestBitString(unittest.TestCase):
    def test_enumerated(self):
        if _debug:
            TestBitString._debug("test_enumerated")

        obj = Enumerated(0)
        assert obj == 0

        obj = Enumerated(1)
        assert obj == 1

        with pytest.raises(TypeError):
            Enumerated(1.0)
        with pytest.raises(ValueError):
            Enumerated("jumped")

    def test_enumerated_fox(self):
        if _debug:
            TestBitString._debug("test_enumerated_fox")

        obj = QuickBrownFox(0)
        assert obj == 0
        assert str(obj) == "quick"

        obj = QuickBrownFox("brown")
        assert obj == 1
        assert str(obj) == "brown"

    def test_enumerated_copy(self):
        if _debug:
            TestBitString._debug("test_enumerated_copy")

        obj1 = Enumerated(0)
        obj2 = Enumerated(obj1)
        assert obj1 == obj2

    def test_enumerated_endec(self):
        if _debug:
            TestBitString._debug("test_enumerated_endec")

        enumerated_endec(0, "00")
        enumerated_endec(1, "01")
        enumerated_endec(127, "7f")
        enumerated_endec(128, "80")
        enumerated_endec(255, "ff")

        enumerated_endec(32767, "7fff")
        enumerated_endec(32768, "8000")

        enumerated_endec(8388607, "7fffff")
        enumerated_endec(8388608, "800000")

        enumerated_endec(2147483647, "7fffffff")
        enumerated_endec(2147483648, "80000000")
