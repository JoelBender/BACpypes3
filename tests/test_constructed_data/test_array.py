#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test ArrayOf
------------
"""

import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.primitivedata import Integer
from bacpypes3.constructeddata import ArrayOf

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def array_of_endec(cls, *args, **kwargs):
    """
    Encode an instance of the class using the keyword arguments, then
    decode the tag list using the class and confirm they are identical.
    """
    if _debug:
        array_of_endec._debug("test_endec %r %r %r", cls, args, kwargs)

    obj1 = cls(*args, **kwargs)
    if _debug:
        array_of_endec._debug("    - obj1: %r", obj1)

    tag_list = obj1.encode()
    if _debug:
        array_of_endec._debug("    - tag_list: %r", tag_list)

    obj2 = cls.decode(tag_list)
    if _debug:
        array_of_endec._debug("    - obj2: %r", obj2)

    assert obj1 == obj2


#
#   Thing000
#


Thing000 = ArrayOf(Integer)


@bacpypes_debugging
class TestThing000(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing000._debug("test_ctor")

        # no ctor parameters
        obj = Thing000()
        assert len(obj) == 0

        # empty array
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

    def test_index(self):
        if _debug:
            TestThing000._debug("test_index")

        # no ctor parameters
        obj = Thing000()
        assert len(obj) == 0

    def test_endec_1(self):
        if _debug:
            TestThing000._debug("test_endec_1")

        # encode and decode
        array_of_endec(Thing000, [4, 5])

    def test_extend(self):
        if _debug:
            TestThing000._debug("test_extend")

        # simple array
        obj = Thing000([1, 2, 3])
        assert len(obj) == 3

        # add an item to the end
        obj.append(4)
        assert len(obj) == 4


#
#   Thing001
#


Thing001 = ArrayOf(Integer, _context=1)


@bacpypes_debugging
class TestThing001(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestThing001._debug("test_endec_1")

        # encode and decode
        array_of_endec(Thing001, [4, 5])
