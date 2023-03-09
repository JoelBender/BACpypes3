#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Sequence
-------------
"""

from copy import deepcopy

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.primitivedata import Tag, TagClass, TagNumber, Integer, Real
from bacpypes3.constructeddata import Sequence
from bacpypes3.json import json_to_sequence, sequence_to_json

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def sequence_endec(cls, **kwargs):
    """
    Encode an instance of the class using the keyword arguments, then
    decode the tag list using the class and confirm they are identical.
    """
    if _debug:
        sequence_endec._debug("test_endec %r %r", cls, kwargs)

    obj1 = cls(**kwargs)
    if _debug:
        sequence_endec._debug("    - obj1: %r", obj1)

    tag_list = obj1.encode()
    if _debug:
        sequence_endec._debug("    - tag_list: %r", tag_list)

    obj2 = cls.decode(tag_list)
    if _debug:
        sequence_endec._debug("    - obj2: %r", obj2)

    assert obj1 == obj2


#
#   Thing000
#


class Thing000(Sequence):
    i: Integer
    j: Real


@bacpypes_debugging
class TestThing000(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing000._debug("test_ctor")

        # no ctor parameters
        obj = Thing000()
        assert obj.i is None
        assert obj.j is None

        # ctor simple parameters
        obj = Thing000(i=1)
        assert obj.i == 1
        assert isinstance(obj.i, Integer)
        assert obj.j is None

        # ctor string parameter
        obj = Thing000(i="1")
        assert obj.i == 1
        assert isinstance(obj.i, Integer)
        assert obj.j is None

        # ctor simple parameter, promote int to float
        obj = Thing000(j=2)
        assert obj.i is None
        assert obj.j == 2.0
        assert isinstance(obj.j, Real)

        # ctor simple parameters
        obj = Thing000(j=2.5)
        assert obj.i is None
        assert obj.j == 2.5
        assert isinstance(obj.j, Real)

        # ctor string parameters, promote string to float
        obj = Thing000(j="3")
        assert obj.i is None
        assert obj.j == 3.0
        assert isinstance(obj.j, Real)

        # ctor string parameters, promote string to float
        obj = Thing000(j="3.5")
        assert obj.i is None
        assert obj.j == 3.5
        assert isinstance(obj.j, Real)

        # dict parameter
        obj = Thing000({"i": 2, "j": 3.5})
        assert obj.i == 2
        assert obj.j == 3.5

        # build from JSON
        obj = json_to_sequence({"i": 2, "j": 3.5}, Thing000)
        assert obj.i == 2
        assert obj.j == 3.5

        # decompose back to JSON
        assert sequence_to_json(obj) == {"i": 2, "j": 3.5}

        with pytest.raises(TypeError):
            Thing000(i=[])
        with pytest.raises(ValueError):
            Thing000(i="snork")

    def test_copy(self):
        if _debug:
            TestThing000._debug("test_copy")

        obj1 = Thing000(i=1, j=2.3)
        obj2 = Thing000(obj1)
        assert obj1 == obj2


#
#   Thing001
#


class Thing001(Sequence):
    i = Integer(_context=1)


@bacpypes_debugging
class TestThing001(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing001._debug("test_ctor")

        # no ctor parameters
        obj = Thing001()
        assert obj.i is None

        # simple ctor parameters
        obj = Thing001(i=1)
        assert obj.i == 1
        assert issubclass(obj.i.__class__, Integer)
        assert obj.i._context == 1

        # round trip from/to JSON
        json = {"i": 2}
        obj = json_to_sequence(deepcopy(json), Thing001)
        assert sequence_to_json(obj) == json


#
#   Thing002
#


class Thing002(Sequence):
    i = Integer(_context=2)


@bacpypes_debugging
class TestThing002(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing002._debug("test_ctor")

        # no ctor parameters
        obj = Thing002()
        assert obj.i is None

        # change value with a plain type, context added
        obj.i = 12
        assert obj.i == 12
        assert issubclass(obj.i.__class__, Integer)
        assert obj.i._context == 2

        # change value with an atomic value, context added
        obj.i = Integer(13)
        assert obj.i == 13
        assert issubclass(obj.i.__class__, Integer)
        assert obj.i._context == 2

        # change value with a context type, context changed
        obj.i = Integer(14, _context=3)
        assert obj.i == 14
        assert issubclass(obj.i.__class__, Integer)
        assert obj.i._context == 2

        # round trip from/to JSON
        json = {"i": 15}
        obj = json_to_sequence(deepcopy(json), Thing002)
        assert sequence_to_json(obj) == json

    def test_copy(self):
        if _debug:
            TestThing002._debug("test_copy")

        # dict parameters
        obj1 = Thing002({"i": 5})
        assert obj1.i == 5

        # make a copy
        obj2 = Thing002(obj1)
        assert obj2.i == 5
        assert issubclass(obj2.i.__class__, Integer)
        assert obj2.i._context == 2


#
#   Thing003
#


class Thing003(Sequence):
    x: Thing000


@bacpypes_debugging
class TestThing003(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing003._debug("test_ctor")

        # no ctor parameters
        obj = Thing003()
        assert obj.x is None

        # empty property value
        obj = Thing003(x={})
        assert isinstance(obj.x, Thing000)

        # wrong property/attribute
        with pytest.raises(AttributeError):
            Thing003(y=2)

        # dict parameter
        obj = Thing003({"x": {"i": 1}})
        assert isinstance(obj.x, Thing000)
        assert isinstance(obj.x.i, Integer)
        assert obj.x.i == 1

        # round trip from/to JSON
        json = {"x": {"i": 2}}
        obj = json_to_sequence(deepcopy(json), Thing003)
        assert sequence_to_json(obj) == json

    def test_copy(self):
        if _debug:
            TestThing003._debug("test_copy")

        # dict parameter
        obj1 = Thing003({"x": {"i": 6}})
        assert obj1.x.i == 6

        # make a copy
        obj2 = Thing003(obj1)
        assert isinstance(obj2.x, Thing000)
        assert isinstance(obj2.x.i, Integer)
        assert obj2.x.i == 6


#
#   Thing004
#


class Thing004(Thing000):
    k: Integer

    def __init__(self, *, k: int = -1, **kwargs):
        super().__init__(**kwargs)
        self.k = k

    def k_func(self) -> Integer:
        return self.k


@bacpypes_debugging
class TestThing004(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestThing004._debug("test_ctor")

        # no ctor parameters
        obj = Thing004()
        assert obj.i is None
        assert obj.k == -1

        # set base class, default value for k
        obj = Thing004(i=3)
        assert obj.i == 3
        assert obj.k == -1

        # round trip from/to JSON
        json = {"i": 4}
        obj = json_to_sequence(deepcopy(json), Thing004)
        assert sequence_to_json(obj) == {"i": 4, "k": -1}

        # no default for i, provide value for k
        obj = Thing004(k=4)
        assert obj.i is None
        assert obj.k == 4

        # round trip from/to JSON
        json = {"k": 5}
        obj = json_to_sequence(deepcopy(json), Thing004)
        assert sequence_to_json(obj) == json


#
#   Thing005
#


class Thing005(Sequence):
    _order = ("i", "j")
    i: Integer
    j: Real


@bacpypes_debugging
class TestThing005(unittest.TestCase):
    def test_endec(self):
        if _debug:
            TestThing005._debug("test_endec")

        # no ctor parameters
        obj = Thing005()
        with pytest.raises(AttributeError):
            obj.encode()

        # no ctor parameters
        obj = Thing005(i=1)
        with pytest.raises(AttributeError):
            obj.encode()

        # no ctor parameters
        obj = Thing005(i=1, j=2.5)
        tag_list = obj.encode()
        assert len(tag_list) == 2
        assert tag_list[0] == Tag(TagClass.application, TagNumber.integer, 1, b"\x01")
        assert tag_list[1] == Tag(
            TagClass.application, TagNumber.real, 4, b"\x40\x20\x00\x00"
        )


#
#   Thing006
#


class Thing006(Sequence):
    _order = ("i", "j")
    i = Integer(_optional=True)
    j = Real()


@bacpypes_debugging
class TestThing006(unittest.TestCase):
    def test_endec(self):
        if _debug:
            TestThing006._debug("test_endec")

        # no ctor parameters
        obj = Thing006()
        with pytest.raises(AttributeError):
            obj.encode()

        # skip optional parameter
        obj = Thing006(j=2.5)
        tag_list = obj.encode()
        assert len(tag_list) == 1
        assert tag_list[0] == Tag(
            TagClass.application, TagNumber.real, 4, b"\x40\x20\x00\x00"
        )

        # no ctor parameters
        obj1 = Thing006(i=2, j=3.5)
        tag_list = obj1.encode()
        assert len(tag_list) == 2
        assert tag_list[0] == Tag(TagClass.application, TagNumber.integer, 1, b"\x02")
        assert tag_list[1] == Tag(
            TagClass.application, TagNumber.real, 4, b"\x40\x60\x00\x00"
        )

        # decode the tag list
        obj2 = Thing006.decode(tag_list)
        assert obj1 == obj2


#
#   Thing007
#


class Thing007(Sequence):
    _order = ("i", "j")
    i: Integer(_optional=True)
    j: Real(_context=1)


@bacpypes_debugging
class TestThing007(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestThing007._debug("test_endec_1")

        # skip optional parameter
        sequence_endec(Thing007, j=4.5)

    def test_endec_2(self):
        if _debug:
            TestThing007._debug("test_endec_2")

        # skip optional parameter
        sequence_endec(Thing007, i=3, j=5.5)


#
#   Thing008
#


class Thing008(Thing007):
    j = 6.5


@bacpypes_debugging
class TestThing008(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestThing008._debug("test_endec_1")

        # pre-initialized value
        sequence_endec(Thing008)
