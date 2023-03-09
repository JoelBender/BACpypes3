#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test ReadPropertyMultiple
---------------
"""

import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.primitivedata import CharacterString
from bacpypes3.constructeddata import Any
from bacpypes3.basetypes import (
    ErrorType,
    ReadAccessSpecification,
    ReadAccessResult,
    ReadAccessResultElement,
    ReadAccessResultElementChoice,
    PropertyReference,
)
from bacpypes3.apdu import (
    ReadPropertyMultipleRequest,
    ReadPropertyMultipleACK,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
def sequence_of_endec(cls, *args, **kwargs):
    """
    Encode an instance of the class using the keyword arguments, then
    decode the tag list using the class and confirm they are identical.
    """
    if _debug:
        sequence_of_endec._debug("test_endec %r %r %r", cls, args, kwargs)

    pdu1 = cls(*args, **kwargs)
    if _debug:
        sequence_of_endec._debug("    - pdu1: %r", pdu1)

    pdu = pdu1.encode()
    if _debug:
        sequence_of_endec._debug("    - pdu: %r", pdu)

    pdu2 = cls.decode(pdu)
    if _debug:
        sequence_of_endec._debug("    - pdu2: %r", pdu2)

    assert pdu1 == pdu2


#
#   ReadPropertyMultipleRequest
#


@bacpypes_debugging
class TestReadPropertyMultipleRequest(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestReadPropertyMultipleRequest._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(
            ReadPropertyMultipleRequest,
            listOfReadAccessSpecs=[
                ReadAccessSpecification(
                    objectIdentifier="analog-input,1",
                    listOfPropertyReferences=[
                        PropertyReference(
                            propertyIdentifier="object-name",
                        )
                    ],
                )
            ],
        )

    def test_endec_2(self):
        if _debug:
            TestReadPropertyMultipleRequest._debug("test_endec_2")

        # encode and decode
        sequence_of_endec(
            ReadPropertyMultipleRequest,
            listOfReadAccessSpecs=[
                ReadAccessSpecification(
                    objectIdentifier="analog-input,1",
                    listOfPropertyReferences=[
                        PropertyReference(
                            propertyIdentifier="object-name",
                            propertyArrayIndex=1,
                        ),
                        PropertyReference(
                            propertyIdentifier="description",
                        ),
                    ],
                )
            ],
        )


@bacpypes_debugging
class TestReadPropertyMultipleACK(unittest.TestCase):
    def test_endec_1(self):
        if _debug:
            TestReadPropertyMultipleACK._debug("test_endec_1")

        # encode and decode
        sequence_of_endec(
            ReadPropertyMultipleACK,
            listOfReadAccessResults=[
                ReadAccessResult(
                    objectIdentifier="analog-input,1",
                    listOfResults=[
                        ReadAccessResultElement(
                            propertyIdentifier="description",
                            readResult=ReadAccessResultElementChoice(
                                propertyValue=Any(CharacterString("snork")),
                            ),
                        ),
                        ReadAccessResultElement(
                            propertyIdentifier="object-name",
                            readResult=ReadAccessResultElementChoice(
                                propertyAccessError=ErrorType(
                                    errorClass="property",
                                    errorCode="outOfMemory",
                                ),
                            ),
                        ),
                    ],
                )
            ],
        )
