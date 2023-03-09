#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Choice
-----------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.primitivedata import Integer, Real
from bacpypes3.constructeddata import Choice

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def choice_endec(cls, **kwargs):
    """
    Encode an instance of the class using the keyword arguments, then
    decode the tag list using the class and confirm they are identical.
    """
    if _debug:
        choice_endec._debug("test_endec %r %r", cls, kwargs)

    obj1 = cls(**kwargs)
    if _debug:
        choice_endec._debug("    - obj1: %r", obj1)

    tag_list = obj1.encode()
    if _debug:
        choice_endec._debug("    - tag_list: %r", tag_list)

    obj2 = cls.decode(tag_list)
    if _debug:
        choice_endec._debug("    - obj2: %r", obj2)

    assert obj1 == obj2


#
#   Thing000
#


class Thing000(Choice):
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
        assert obj._choice is None

        # set the choice
        obj.i = 1
        assert obj.i == 1
        assert isinstance(obj.i, Integer)
        assert obj._choice == "i"
        assert obj.j is None

        # change the choice
        obj.j = 2.5
        assert obj.i is None
        assert isinstance(obj.j, Real)
        assert obj._choice == "j"
        assert obj.j == 2.5

        # clear the choice
        obj.j = None
        assert obj.i is None
        assert obj.j is None

    def test_ctor_kwarg(self):
        if _debug:
            TestThing000._debug("test_ctor_kwarg")

        # pick a parameter
        obj = Thing000(i=2)
        assert obj.i == 2
        assert obj._choice == "i"

        # multiple parameters an error
        with pytest.raises(RuntimeError):
            Thing000(i=2, j=3.5)

    def test_ctor_dict(self):
        if _debug:
            TestThing000._debug("test_ctor_dict")

        # pick a parameter
        obj = Thing000({"i": 3})
        assert obj.i == 3
        assert obj._choice == "i"

        # wrong attribute
        with pytest.raises(AttributeError):
            Thing000({"k": 4})

        # multiple parameters an error
        with pytest.raises(RuntimeError):
            Thing000({"i": 4, "j": 5.5})

    def test_copy(self):
        if _debug:
            TestThing000._debug("test_copy")

        obj1 = Thing000(i=1)
        obj2 = Thing000(obj1)
        assert obj1 == obj2

    def test_endec_1(self):
        if _debug:
            TestThing000._debug("test_endec_1")

        # encode and decode
        choice_endec(Thing000, j=4.5)
