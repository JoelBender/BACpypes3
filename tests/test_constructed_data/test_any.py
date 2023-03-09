#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Any
--------
"""

import inspect
import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.primitivedata import Integer
from bacpypes3.constructeddata import Any, Sequence

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def any_endec(cls, *args, **kwargs):
    """
    Encode an instance of the class using the arguments and keyword arguments,
    then decode the tag list using the class and confirm they are identical.
    """
    if _debug:
        any_endec._debug("test_endec %r %r", cls, kwargs)

    obj1 = cls(*args, **kwargs)
    if _debug:
        any_endec._debug("    - obj1: %r", obj1)

    tag_list = obj1.encode()
    if _debug:
        any_endec._debug("    - tag_list: %r", tag_list)

    obj2 = cls.decode(tag_list)
    if _debug:
        any_endec._debug("    - obj2: %r", obj2)

    assert obj1 == obj2


@bacpypes_debugging
class TestAny000(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestAny000._debug("test_ctor")

        # no ctor parameters is a class
        cls = Any()
        assert inspect.isclass(cls)

        # context decorator still a class
        cls = Any(_context=1)
        assert inspect.isclass(cls)

        # pass None is uninitialized
        obj = Any(None)
        assert isinstance(obj, Any)
        assert obj.tagList is None

    def test_atomic_ctor(self):
        if _debug:
            TestAny000._debug("test_atomic_ctor")

        # ctor atomic parameter
        obj = Any(Integer(1))
        assert obj.tagList

    def test_cast(self):
        if _debug:
            TestAny000._debug("test_cast")

        value = Integer(2)

        obj1 = Any(None)
        obj1.cast_in(value)
        obj2 = obj1.cast_out(Integer)
        assert obj2 == value

    def test_copy(self):
        if _debug:
            TestAny000._debug("test_copy")

        obj1 = Any(Integer(1))
        obj2 = Any(obj1)
        assert obj1 == obj2


#
#   Thing001
#


class Thing001(Sequence):
    _order = ("i",)
    i: Integer(_context=1)


@bacpypes_debugging
class TestAny001(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestAny001._debug("test_ctor")

        # ctor nonatomic parameter
        obj = Any(Thing001(i=1))
        assert obj.tagList

    def test_cast(self):
        if _debug:
            TestAny001._debug("test_cast")

        value = Thing001(i=2)

        obj1 = Any(None)
        obj1.cast_in(value)
        obj2 = obj1.cast_out(Thing001)
        assert obj2 == value
