#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Null
---------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, Null

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def null_tag(x):
    """Convert a hex string to a null application tag."""
    if _debug:
        null_tag._debug("null_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.null, len(b), b)
    if _debug:
        null_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def null_encode(obj):
    """Encode a Null object into a tag."""
    if _debug:
        null_encode._debug("null_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        null_encode._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def null_decode(tag):
    """Decode a null from a tag."""
    if _debug:
        null_decode._debug("null_decode %r", tag)

    obj = Null.decode(TagList([tag]))
    if _debug:
        null_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def null_endec(v, x):
    """Pass the value to Null, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        null_endec._debug("null_endec %r %r", v, x)

    obj = Null(v)
    if _debug:
        null_endec._debug("    - obj: %r", obj)

    tag = null_tag(x)
    if _debug:
        null_endec._debug("    - tag: %r, %r", tag, tag.tag_data)

    assert null_encode(obj) == tag
    assert null_decode(tag) == obj


@bacpypes_debugging
class TestNull(unittest.TestCase):
    def test_null(self):
        if _debug:
            TestNull._debug("test_null")

        obj = Null(())
        assert obj == ()

        obj = Null([])
        assert obj == ()

        obj = Null("null")
        assert obj == ()

        with pytest.raises(ValueError):
            Null("some string")
        with pytest.raises(TypeError):
            Null(1.0)

    def test_null_copy(self):
        if _debug:
            TestNull._debug("test_null_copy")

        obj1 = Null(())
        obj2 = Null(obj1)
        assert obj2 == ()

    def test_null_endec(self):
        if _debug:
            TestNull._debug("test_null_endec")

        null_endec((), "")
