#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Double
-----------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, Double

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def double_tag(x):
    """Convert a hex string to a real application tag."""
    if _debug:
        double_tag._debug("double_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.double, len(b), b)
    if _debug:
        double_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def double_encode(obj):
    """Encode a Double object into a tag."""
    if _debug:
        double_encode._debug("double_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        double_encode._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def double_decode(tag):
    """Decode a Double from a tag."""
    if _debug:
        double_decode._debug("double_decode %r", tag)

    obj = Double.decode(TagList([tag]))
    if _debug:
        double_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def double_endec(v, x):
    """Pass the value to Double, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        double_endec._debug("double_endec %r %r", v, x)

    obj = Double(v)
    if _debug:
        double_endec._debug("    - obj: %r", obj)

    tag = double_tag(x)
    if _debug:
        double_endec._debug("    - tag: %r", tag)
        tag.debug_contents()

    assert double_encode(obj) == tag
    assert double_decode(tag) == obj


@bacpypes_debugging
class TestDouble(unittest.TestCase):
    def test_double(self):
        if _debug:
            TestDouble._debug("test_double")

        obj = Double(0.0)
        assert obj == 0.0

        obj = Double(1.5)
        assert obj == 1.5

        obj = Double("2.5")
        assert obj == 2.5

        with pytest.raises(ValueError):
            Double("some string")

    def test_double_copy(self):
        if _debug:
            TestDouble._debug("test_double_copy")

        obj1 = Double(3.4)
        obj2 = Double(obj1)
        assert obj1 == obj2

    def test_double_endec(self):
        if _debug:
            TestDouble._debug("test_double_endec")

        double_endec(0, "0000000000000000")
        double_endec(1, "3ff0000000000000")
        double_endec(-1, "bff0000000000000")

        double_endec(73.5, "4052600000000000")

        inf = float("inf")
        double_endec(inf, "7ff0000000000000")
        double_endec(-inf, "fff0000000000000")

        # nan not the same nan
        # nan = float('nan')
        # double_endec(nan, '7ff8000000000000')
