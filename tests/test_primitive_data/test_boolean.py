#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Boolean
------------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, Boolean

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def boolean_tag(x):
    """Convert a hex string to a null application tag."""
    if _debug:
        boolean_tag._debug("boolean_tag %r", x)

    tag = Tag(TagClass.application, TagNumber.boolean, x, b"")
    if _debug:
        boolean_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def boolean_encode(obj):
    """Encode a Boolean object into a tag."""
    if _debug:
        boolean_encode._debug("boolean_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        boolean_encode._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def boolean_decode(tag):
    """Decode a null from a tag."""
    if _debug:
        boolean_decode._debug("boolean_decode %r", tag)

    obj = Boolean.decode(TagList([tag]))
    if _debug:
        boolean_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def boolean_endec(v, x):
    """Pass the value to Boolean, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        boolean_endec._debug("boolean_endec %r %r", v, x)

    obj = Boolean(v)
    if _debug:
        boolean_endec._debug("    - obj: %r", obj)

    tag = boolean_tag(x)
    if _debug:
        boolean_endec._debug("    - tag: %r, %r", tag, tag.tag_data)

    assert boolean_encode(obj) == tag
    assert boolean_decode(tag) == obj


@bacpypes_debugging
class TestBoolean(unittest.TestCase):
    def test_boolean(self):
        if _debug:
            TestBoolean._debug("test_boolean")

        # booleans cannot extend bool, so they are int values 1 or 0
        obj = Boolean(0)
        assert obj == 0

        with pytest.raises(ValueError):
            Boolean("some string")
        with pytest.raises(TypeError):
            Boolean(1.0)

    def test_boolean_value(self):
        if _debug:
            TestBoolean._debug("test_boolean_value")

        obj = Boolean(True)
        assert obj == 1

    def test_boolean_copy(self):
        if _debug:
            TestBoolean._debug("test_boolean_copy")

        obj1 = Boolean(0)
        obj2 = Boolean(obj1)
        assert obj1 == obj2

    def test_boolean_endec(self):
        if _debug:
            TestBoolean._debug("test_boolean_endec")

        boolean_endec(False, 0)
        boolean_endec(True, 1)
