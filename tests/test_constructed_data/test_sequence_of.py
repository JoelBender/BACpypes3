#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test SequenceOf
---------------
"""

import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.primitivedata import Integer, Real
from bacpypes3.constructeddata import Sequence, SequenceOf

# some debugging
_debug = 0
_log = ModuleLogger(globals())


class ThingA(Sequence):
    _order = ("i", "j")
    i: Integer
    j: Real


@bacpypes_debugging
def sequence_of_endec(cls, *args, **kwargs):
    """
    Encode an instance of the class using the keyword arguments, then
    decode the tag list using the class and confirm they are identical.
    """
    if _debug:
        sequence_of_endec._debug("test_endec %r %r %r", cls, args, kwargs)

    obj1 = cls(*args, **kwargs)
    if _debug:
        sequence_of_endec._debug("    - obj1: %r", obj1)

    tag_list = obj1.encode()
    if _debug:
        sequence_of_endec._debug("    - tag_list: %r", tag_list)
        for i, tag in enumerate(tag_list):
            sequence_of_endec._debug("        [%d] %r", i, tag)

    obj2 = cls.decode(tag_list)
    if _debug:
        sequence_of_endec._debug("    - obj2: %r", obj2)
        for i, obj in enumerate(obj2):
            sequence_of_endec._debug("        [%d] %r", i, obj)

    assert obj1 == obj2


#
#   Thing001
#


Thing001 = SequenceOf(Integer)


@bacpypes_debugging
class TestThing001(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing001._debug("test_ctor")

        # no ctor parameters
        obj = Thing001()
        assert len(obj) == 0

        # empty list
        obj = Thing001([])
        assert len(obj) == 0

        # single element
        obj = Thing001([1])
        assert len(obj) == 1
        assert isinstance(obj[0], Integer)

    def test_copy(self):
        if _debug:
            TestThing001._debug("test_copy")

        obj1 = Thing001([1, 2, 3])
        obj2 = Thing001(obj1)
        assert obj1 == obj2

    def test_endec_1(self):
        if _debug:
            TestThing001._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(Thing001, [])

    def test_endec_2(self):
        if _debug:
            TestThing001._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(Thing001, [4, 5])


#
#   Thing002
#


Thing002 = SequenceOf(Integer, _context=1)


@bacpypes_debugging
class TestThing002(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestThing002._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(Thing002, [])

    def test_endec_2(self):
        if _debug:
            TestThing002._debug("test_endec_2")

        # encode and decode
        sequence_of_endec(Thing002, [4, 5])


#
#   Thing003
#


class ThingB(Sequence):
    _order = ("i", "j")
    i: Integer
    j: Real


Thing003 = SequenceOf(ThingB)


@bacpypes_debugging
class TestThing003(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestThing003._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(Thing003, [])

    def test_endec_2(self):
        if _debug:
            TestThing003._debug("test_endec_2")

        # encode and decode
        sequence_of_endec(Thing003, [ThingB(i=1, j=2.5)])

    def test_endec_3(self):
        if _debug:
            TestThing003._debug("test_endec_3")

        # encode and decode
        sequence_of_endec(Thing003, [ThingB(i=1, j=2.5), ThingB(i=6, j=7.5)])


#
#   Thing004
#


Thing004 = SequenceOf(ThingB, _context=2)


@bacpypes_debugging
class TestThing004(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestThing004._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(Thing004, [])

    def test_endec_2(self):
        if _debug:
            TestThing004._debug("test_endec_2")

        # encode and decode
        sequence_of_endec(Thing004, [ThingB(i=1, j=2.5)])

    def test_endec_3(self):
        if _debug:
            TestThing004._debug("test_endec_3")

        # encode and decode
        sequence_of_endec(Thing004, [ThingB(i=1, j=2.5), ThingB(i=6, j=7.5)])


#
#   Thing005
#


class ThingC(Sequence):
    _order = ("i", "j")
    i = Integer(_context=0)
    j = Real(_optional=True)


Thing005 = SequenceOf(ThingC)


@bacpypes_debugging
class TestThing005(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestThing005._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(Thing005, [])

    def test_endec_2(self):
        if _debug:
            TestThing005._debug("test_endec_2")

        # encode and decode
        sequence_of_endec(Thing005, [ThingC(i=1)])

    def test_endec_3(self):
        if _debug:
            TestThing005._debug("test_endec_3")

        # encode and decode
        sequence_of_endec(Thing005, [ThingC(i=1, j=2.5), ThingC(i=6)])


#
#   Thing006
#


Thing006 = SequenceOf(ThingC, _context=2)


@bacpypes_debugging
class TestThing006(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestThing006._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(Thing006, [])

    def test_endec_2(self):
        if _debug:
            TestThing006._debug("test_endec_2")

        # encode and decode
        sequence_of_endec(Thing006, [ThingC(i=1)])

    def test_endec_3(self):
        if _debug:
            TestThing006._debug("test_endec_3")

        # encode and decode
        sequence_of_endec(Thing006, [ThingC(i=1, j=2.5), ThingC(i=6)])


#
#   Thing007
#


class ThingD(Sequence):
    _order = ("i",)
    i = SequenceOf(Integer, _context=1)


Thing007 = SequenceOf(ThingD)


@bacpypes_debugging
class TestThing007(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing007._debug("test_ctor")

        # no ctor parameters
        obj = ThingD()
        assert obj.i is None

        # empty list
        obj = ThingD(i=[])
        assert len(obj.i) == 0

        # single element
        obj = ThingD(i=[1])
        assert len(obj.i) == 1
        assert isinstance(obj.i[0], Integer)

    def test_copy(self):
        if _debug:
            TestThing007._debug("test_copy")

        obj1 = ThingD(i=[1, 2, 3])
        obj2 = ThingD(obj1)
        assert obj1 == obj2

    def test_endec_1(self):
        if _debug:
            TestThing007._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(Thing007, [])

    def test_endec_2(self):
        if _debug:
            TestThing007._debug("test_endec_2")

        # encode and decode
        sequence_of_endec(Thing007, [ThingD(i=[])])

    def test_endec_3(self):
        if _debug:
            TestThing007._debug("test_endec_3")

        # encode and decode
        sequence_of_endec(Thing007, [ThingD(i=[1]), ThingD(i=[2])])

    def test_endec_4(self):
        if _debug:
            TestThing007._debug("test_endec_4")

        # encode and decode
        sequence_of_endec(Thing007, [ThingD(i=[]), ThingD(i=[1, 2])])


#
#   Thing008
#


class ThingE(Sequence):
    _order = ("i", "j")
    i = Integer(_context=0)
    j = SequenceOf(Integer, _context=1)


Thing008 = SequenceOf(ThingE)


@bacpypes_debugging
class TestThing008(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing008._debug("test_ctor")

        # no ctor parameters
        obj = ThingE()
        assert obj.j is None

        # empty list
        obj = ThingE(j=[])
        assert len(obj.j) == 0

        # single element
        obj = ThingE(j=[1])
        assert len(obj.j) == 1
        assert isinstance(obj.j[0], Integer)

    def test_copy(self):
        if _debug:
            TestThing008._debug("test_copy")

        obj1 = ThingE(i=1, j=[2, 3, 4])
        obj2 = ThingE(obj1)
        assert obj1 == obj2

    def test_endec_1(self):
        if _debug:
            TestThing008._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(Thing008, [])

    def test_endec_2(self):
        if _debug:
            TestThing008._debug("test_endec_2")

        # encode and decode
        sequence_of_endec(Thing008, [ThingE(i=1, j=[])])

    def test_endec_3(self):
        if _debug:
            TestThing008._debug("test_endec_3")

        # encode and decode
        sequence_of_endec(Thing008, [ThingE(i=2, j=[3]), ThingE(i=4, j=[5, 6])])
