#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Tag
--------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.pdu import PDUData
from bacpypes3.primitivedata import (
    Tag,
    ContextTag,
    OpeningTag,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def tag_tuple(tag):
    """Simple function to decompose a tag for debugging."""
    return (tag.tagClass, tag.tagNumber, tag.tagLVT, tag.tagData)


@bacpypes_debugging
def context_encode(tag):
    """Encode the tag, return the data."""
    if _debug:
        context_encode._debug("context_encode %r", tag)

    return tag.encode().pduData


@bacpypes_debugging
def context_decode(blob):
    """Build PDU from the byte string, decode the tag."""
    if _debug:
        context_decode._debug("context_decode %r", blob)

    tag = Tag.decode(PDUData(blob))
    # assert isinstance(tag, ContextTag)

    return tag


@bacpypes_debugging
def context_endec(tnum, x, y):
    """Convert the value (a primitive object) to a hex encoded string,
    convert the hex encoded string to and object, and compare the results to
    each other."""
    if _debug:
        context_endec._debug("context_endec %r %r %r", tnum, x, y)

    # convert the hex strings to bytes
    tdata = xtob(x)
    blob1 = xtob(y)

    # make a context tag
    tag1 = ContextTag(tnum, tdata)

    # decode the blob into a tag
    tag2 = context_decode(blob1)
    if _debug:
        context_endec._debug("    - tag2: %r", tag2)

    # encode the tag into a blob
    blob2 = context_encode(tag1)
    if _debug:
        context_endec._debug("    - blob2: %r", blob2)

    # compare the results
    assert tag1 == tag2
    assert blob1 == blob2


@bacpypes_debugging
class TestContextTag(unittest.TestCase):
    def test_context_tag(self):
        if _debug:
            TestContextTag._debug("test_context_tag")

        # test context tag construction
        ContextTag(0, xtob(""))

        # missing 2 required positional arguments
        with pytest.raises(TypeError):
            ContextTag()

        # test encoding and decoding
        context_endec(0, "", "08")
        context_endec(1, "01", "1901")
        context_endec(2, "0102", "2A0102")
        context_endec(3, "010203", "3B010203")
        context_endec(14, "010203", "EB010203")
        context_endec(15, "010203", "FB0F010203")


@bacpypes_debugging
def opening_encode(tag):
    """Encode the tag, return the data."""
    if _debug:
        opening_encode._debug("opening_encode %r", tag)

    return tag.encode().pduData


@bacpypes_debugging
def opening_decode(blob):
    """Build PDU from the byte string, decode the tag."""
    if _debug:
        opening_decode._debug("opening_decode %r", blob)

    tag = Tag.decode(PDUData(blob))
    # assert isinstance(tag, OpeningTag)

    return tag


@bacpypes_debugging
def opening_endec(tnum, x):
    """Convert the value (a primitive object) to a hex encoded string,
    convert the hex encoded string to and object, and compare the results to
    each other."""
    if _debug:
        opening_endec._debug("opening_endec %r %r", tnum, x)

    # convert the hex string to a blob
    blob1 = xtob(x)

    # make a context tag
    tag1 = OpeningTag(tnum)
    if _debug:
        opening_endec._debug("    - tag1: %r", tag1)

    # decode the blob into a tag
    tag2 = opening_decode(blob1)
    if _debug:
        opening_endec._debug("    - tag2: %r", tag2)

    # encode the tag into a blob
    blob2 = opening_encode(tag1)
    if _debug:
        opening_endec._debug("    - blob2: %r", blob2)

    # compare the results
    assert tag1 == tag2
    assert blob1 == blob2


@bacpypes_debugging
class TestOpeningTag(unittest.TestCase):
    def test_opening_tag(self):
        if _debug:
            TestOpeningTag._debug("test_opening_tag")

        # test opening tag construction
        OpeningTag(0)
        with pytest.raises(TypeError):
            OpeningTag()

        # test encoding, and decoding
        opening_endec(0, "0E")
        opening_endec(1, "1E")
        opening_endec(2, "2E")
        opening_endec(3, "3E")
        opening_endec(14, "EE")
        opening_endec(15, "FE0F")
        opening_endec(254, "FEFE")
