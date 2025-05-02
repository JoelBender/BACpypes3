#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test WhoHas
-----------
"""

import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.basetypes import WhoHasObject, WhoHasLimits
from bacpypes3.apdu import WhoHasRequest

# some debugging
_debug = 0
_log = ModuleLogger(globals())

@bacpypes_debugging
class TestWhoHasRequest(unittest.TestCase):
    def test_endec_01(self):
        if _debug:
            TestWhoHasRequest._debug("test_endec_01")

        x = WhoHasRequest(
            limits=WhoHasLimits(
                deviceInstanceRangeLowLimit=0,
                deviceInstanceRangeHighLimit=999,
            ),
            object=WhoHasObject(
                objectIdentifier='analog-value,1'
            ),
        )
        if _debug:
            TestWhoHasRequest._debug("    - x: %r", x)

        y = x.encode()
        if _debug:
            TestWhoHasRequest._debug("    - y: %r", y)

        z = WhoHasRequest.decode(y)
        if _debug:
            TestWhoHasRequest._debug("    - z: %r", z)

    def test_endec_02(self):
        if _debug:
            TestWhoHasRequest._debug("test_endec_02")

        x = WhoHasRequest(
            object=WhoHasObject(
                objectIdentifier='analog-value,1'
            ),
        )
        if _debug:
            TestWhoHasRequest._debug("    - x: %r", x)

        y = x.encode()
        if _debug:
            TestWhoHasRequest._debug("    - y: %r", y)

        z = WhoHasRequest.decode(y)
        if _debug:
            TestWhoHasRequest._debug("    - z: %r", z)

