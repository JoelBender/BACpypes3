#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Date
---------
"""

import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.primitivedata import Date, Time
from bacpypes3.basetypes import DateTime

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class TestDateTime(unittest.TestCase):
    def test_ctor(self):
        if _debug:
            TestDateTime._debug("test_ctor")

        # no ctor parameters
        obj = DateTime()
        assert obj.date is None
        assert obj.time is None

        # ctor simple parameters
        assert DateTime("2025-01-01") == DateTime(date=(125, 1, 1, 3), time=(0, 0, 0, 0))
        assert DateTime("2025-01-01 12:34:56") == DateTime(date=(125, 1, 1, 3), time=(12, 34, 56, 0))
        assert DateTime("2025-01-01 12:34:56.7") == DateTime(date=(125, 1, 1, 3), time=(12, 34, 56, 70))
        assert DateTime("2025-01-01 12:34:56.78") == DateTime(date=(125, 1, 1, 3), time=(12, 34, 56, 78))
        assert DateTime("2025-01-01 12:34:56.789") == DateTime(date=(125, 1, 1, 3), time=(12, 34, 56, 78))

        assert DateTime("2025-01-01 mon") == DateTime(date=(125, 1, 1, 1), time=(0, 0, 0, 0))
