#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test ListOf
-----------
"""

import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.primitivedata import Integer
from bacpypes3.constructeddata import ListOf

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def list_of_endec(cls, *args, **kwargs):
    """
    Encode an instance of the class using the keyword arguments, then
    decode the tag list using the class and confirm they are identical.
    """
    if _debug:
        list_of_endec._debug("test_endec %r %r %r", cls, args, kwargs)

    obj1 = cls(*args, **kwargs)
    if _debug:
        list_of_endec._debug("    - obj1: %r", obj1)

    tag_list = obj1.encode()
    if _debug:
        list_of_endec._debug("    - tag_list: %r", tag_list)

    obj2 = cls.decode(tag_list)
    if _debug:
        list_of_endec._debug("    - obj2: %r", obj2)

    assert obj1 == obj2


#
#   Thing000
#


Thing000 = ListOf(Integer)


@bacpypes_debugging
class TestThing000(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing000._debug("test_ctor")

        # no ctor parameters
        obj = Thing000()
        assert len(obj) == 0

        # empty list
        obj = Thing000([])
        assert len(obj) == 0

        # single element
        obj = Thing000([1])
        assert len(obj) == 1
        assert isinstance(obj[0], Integer)

    def test_copy(self):
        if _debug:
            TestThing000._debug("test_copy")

        obj1 = Thing000([1, 2, 3])
        obj2 = Thing000(obj1)
        assert obj1 == obj2

    def test_endec_1(self):
        if _debug:
            TestThing000._debug("test_endec_1")

        # encode and decode
        list_of_endec(Thing000, [4, 5])


#
#   Thing001
#


Thing001 = ListOf(Integer, _context=1)


@bacpypes_debugging
class TestThing001(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestThing001._debug("test_endec_1")

        # encode and decode
        list_of_endec(Thing001, [4, 5])
