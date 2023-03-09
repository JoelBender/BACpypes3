#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test ObjectIdentifier
--------------------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob, btox
from bacpypes3.primitivedata import (
    Tag,
    TagClass,
    TagNumber,
    TagList,
    ObjectType,
    ObjectIdentifier,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


class CustomType(ObjectType):
    customInput = 128
    customOutput = 129


class CustomIdentifier(ObjectIdentifier):
    object_type_class: type = CustomType


@bacpypes_debugging
def object_identifier_tag(x):
    """Convert a hex string to an octet string application tag."""
    if _debug:
        object_identifier_tag._debug("object_identifier_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.objectIdentifier, len(b), b)
    if _debug:
        object_identifier_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def object_identifier_encode(obj):
    """Encode a ObjectIdentifier object into a tag."""
    if _debug:
        object_identifier_encode._debug("object_identifier_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        object_identifier_encode._debug("    - tag: %r ,%r", tag, btox(tag.tag_data))

    return tag


@bacpypes_debugging
def object_identifier_decode(tag):
    """Decode a ObjectIdentifier from a tag."""
    if _debug:
        object_identifier_decode._debug("object_identifier_decode %r", tag)

    obj = ObjectIdentifier.decode(TagList([tag]))
    if _debug:
        object_identifier_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def object_identifier_endec(v, x):
    """Pass the value to ObjectIdentifier, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        object_identifier_endec._debug("object_identifier_endec %r %r", v, x)

    obj = ObjectIdentifier((0, 1))
    tag = object_identifier_tag(x)

    assert object_identifier_encode(obj) == tag
    assert object_identifier_decode(tag) == obj


@bacpypes_debugging
class TestObjectIdentifier(unittest.TestCase):
    def test_object_identifier(self):
        if _debug:
            TestObjectIdentifier._debug("test_object_identifier")

        obj = ObjectIdentifier((0, 1))
        assert obj == (0, 1)
        assert str(obj) == "analog-input,1"

        obj = ObjectIdentifier("binary-input,2")
        assert obj == (3, 2)

        obj = ObjectIdentifier(20971523)
        assert obj == (5, 3)
        assert str(obj) == "binary-value,3"

    def test_custom_identifier(self):
        if _debug:
            TestObjectIdentifier._debug("test_custom_identifier")

        obj = CustomIdentifier((0, 1))
        assert obj == (0, 1)
        assert str(obj) == "analog-input,1"

        obj = CustomIdentifier("customInput:2")
        assert obj == (128, 2)

        obj = CustomIdentifier("custom-input,2")
        assert obj == (128, 2)

        obj = CustomIdentifier(541065219)
        assert obj == (129, 3)
        assert str(obj) == "custom-output,3"

        with pytest.raises(TypeError):
            ObjectIdentifier(b"some bytes")
        with pytest.raises(ValueError):
            ObjectIdentifier("some string")

    def test_object_identifier_copy(self):
        if _debug:
            TestObjectIdentifier._debug("test_object_identifier_copy")

        obj1 = ObjectIdentifier((6, 7))
        obj2 = ObjectIdentifier(obj1)
        assert obj1 == obj2

    def test_object_identifier_endec(self):
        if _debug:
            TestObjectIdentifier._debug("test_object_identifier_endec")

        # object_identifier_endec("", "00")
        # object_identifier_endec("abc", "00616263")
