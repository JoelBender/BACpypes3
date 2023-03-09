#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test CharacterString
--------------------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob, btox
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, TagList, CharacterString

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def character_string_tag(x):
    """Convert a hex string to an octet string application tag."""
    if _debug:
        character_string_tag._debug("character_string_tag %r", x)

    b = xtob(x)
    tag = Tag(TagClass.application, TagNumber.characterString, len(b), b)
    if _debug:
        character_string_tag._debug("    - tag: %r", tag)

    return tag


@bacpypes_debugging
def character_string_encode(obj):
    """Encode a CharacterString object into a tag."""
    if _debug:
        character_string_encode._debug("character_string_encode %r", obj)

    tag = obj.encode()[0]
    if _debug:
        character_string_encode._debug("    - tag: %r ,%r", tag, btox(tag.tag_data))

    return tag


@bacpypes_debugging
def character_string_decode(tag):
    """Decode a CharacterString from a tag."""
    if _debug:
        character_string_decode._debug("character_string_decode %r", tag)

    obj = CharacterString.decode(TagList([tag]))
    if _debug:
        character_string_decode._debug("    - obj: %r", obj)

    return obj


@bacpypes_debugging
def character_string_endec(v, x):
    """Pass the value to CharacterString, construct a tag from the hex string,
    and compare results of encoding and decoding."""
    if _debug:
        character_string_endec._debug("character_string_endec %r %r", v, x)

    obj = CharacterString(v)
    if _debug:
        character_string_endec._debug("    - obj: %r", obj)

    tag = character_string_tag(x)
    if _debug:
        character_string_endec._debug("    - tag: %r, %r", tag, btox(tag.tag_data))

    assert character_string_encode(obj) == tag
    if _debug:
        character_string_endec._debug("    - 1")

    assert character_string_decode(tag) == obj
    if _debug:
        character_string_endec._debug("    - 2")


@bacpypes_debugging
class TestCharacterString(unittest.TestCase):
    def test_character_string(self):
        if _debug:
            TestCharacterString._debug("test_character_string")

        obj = CharacterString("")
        assert obj == ""

        with pytest.raises(TypeError):
            CharacterString(1)
        with pytest.raises(TypeError):
            CharacterString(b"some bytes")

    def test_character_string_copy(self):
        if _debug:
            TestCharacterString._debug("test_character_string_copy")

        obj1 = CharacterString("")
        obj2 = CharacterString(obj1)
        assert obj1 == obj2

    def test_character_string_endec(self):
        if _debug:
            TestCharacterString._debug("test_character_string_endec")

        character_string_endec("", "00")
        character_string_endec("abc", "00616263")

        # some controllers encoding character string mixing latin-1 and utf-8
        # try to cover those cases without failing
        character_string_endec("0\N{DEGREE SIGN}C", "0030c2b043")
