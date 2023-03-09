#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Real
---------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, Real

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def real_tag(x):
    """Convert a hex string to a real application tag."""
    if _debug:
        real_tag._debug("real_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.real, len(b), b)
    if _debug:
        real_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def real_encode(obj):
    """Encode a Real object into a tag."""
    if _debug:
        real_encode._debug("real_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        real_encode._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def real_decode(tag):
    """Decode a Real from a tag."""
    if _debug:
        real_decode._debug("real_decode %r", tag)

    obj = Real.decode(TagList([tag]))
    if _debug:
        real_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def real_endec(v, x):
    """Pass the value to Real, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        real_endec._debug("real_endec %r %r", v, x)

    obj = Real(v)
    if _debug:
        real_endec._debug("    - obj: %r", obj)

    tag = real_tag(x)
    if _debug:
        real_endec._debug("    - tag: %r", tag)
        tag.debug_contents()

    assert real_encode(obj) == tag
    assert real_decode(tag) == obj


@bacpypes_debugging
class TestReal(unittest.TestCase):
    def test_unsigned(self):
        if _debug:
            TestReal._debug("test_unsigned")

        obj = Real(0.0)
        assert obj == 0

        obj = Real(1.5)
        assert obj == 1.5

        obj = Real("2.5")
        assert obj == 2.5

        with pytest.raises(ValueError):
            Real("some string")

    def test_real_value(self):
        if _debug:
            TestReal._debug("test_real_value")

        obj = Real(1)
        assert obj == 1

    def test_real_copy(self):
        if _debug:
            TestReal._debug("test_real_copy")

        obj1 = Real(4.6)
        obj2 = Real(obj1)
        assert obj1 == obj2

    def test_real_endec(self):
        if _debug:
            TestReal._debug("test_real_endec")

        real_endec(0, "00000000")
        real_endec(1, "3f800000")
        real_endec(-1, "bf800000")

        real_endec(73.5, "42930000")

        inf = float("inf")
        real_endec(inf, "7f800000")
        real_endec(-inf, "ff800000")

        # nan not the same nan
        # nan = float('nan')
        # real_endec(nan, '7fc00000')
