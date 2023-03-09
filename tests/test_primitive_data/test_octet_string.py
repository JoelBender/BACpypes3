#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test OctetString
----------------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, OctetString

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def octet_string_tag(x):
    """Convert a hex string to an octet string application tag."""
    if _debug:
        octet_string_tag._debug("octet_string_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.octetString, len(b), b)
    if _debug:
        octet_string_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def octet_string_encode(obj):
    """Encode a OctetString object into a tag."""
    if _debug:
        octet_string_encode._debug("octet_string_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        octet_string_encode._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def octet_string_decode(tag):
    """Decode a OctetString from a tag."""
    if _debug:
        octet_string_decode._debug("octet_string_decode %r", tag)

    obj = OctetString.decode(TagList([tag]))
    if _debug:
        octet_string_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def octet_string_endec(x):
    """Pass the value to OctetString, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        octet_string_endec._debug("octet_string_endec %r", x)

    b = xtob(x)
    obj = OctetString(b)
    if _debug:
        octet_string_endec._debug("    - obj: %r", obj)

    tag = octet_string_tag(x)
    if _debug:
        octet_string_endec._debug("    - tag: %r", tag)
        tag.debug_contents()

    assert octet_string_encode(obj) == tag
    assert octet_string_decode(tag) == obj


@bacpypes_debugging
class TestOctetString(unittest.TestCase):
    def test_octet_string(self):
        if _debug:
            TestOctetString._debug("test_octet_string")

        obj = OctetString(b"")
        assert obj == b""

        with pytest.raises(TypeError):
            OctetString(1)
        with pytest.raises(TypeError):
            OctetString("some string")

    def test_octet_string_copy(self):
        if _debug:
            TestOctetString._debug("test_octet_string_copy")

        obj1 = OctetString(b"123")
        obj2 = OctetString(obj1)
        assert obj1 == obj2

    def test_octet_string_endec(self):
        if _debug:
            TestOctetString._debug("test_octet_string_endec")

        octet_string_endec("")
        octet_string_endec("01")
        octet_string_endec("0102")
        octet_string_endec("010203")
        octet_string_endec("01020304")
