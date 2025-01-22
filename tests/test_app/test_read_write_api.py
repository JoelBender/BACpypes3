#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test read_property(), write_property() API
------------------------------------------
"""

import asyncio
import unittest
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

from bacpypes3.errors import AbortOther
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import (
    Unsigned,
    ObjectType,
    ObjectIdentifier,
    PropertyIdentifier,
)
from bacpypes3.basetypes import DeviceStatus
from bacpypes3.constructeddata import Any
from bacpypes3.apdu import (
    APDU,
    ReadPropertyRequest,
    WritePropertyRequest,
    ReadPropertyMultipleRequest,
    ReadAccessSpecification,
)
from bacpypes3.app import Application

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class MatchApplication(Application):
    """
    Instances of this class are used to match a request.
    """

    def __init__(self, match_apdu: APDU, *args, **kwds):
        if _debug:
            MatchApplication.debug("__init__ %r", match_apdu)

        self.match_apdu = match_apdu

        return super().__init__(*args, **kwds)

    def request(self, apdu: APDU) -> asyncio.Future:
        """
        Trap the request call to see if it matches the one we are looking for.
        """
        if _debug:
            MatchApplication.debug("request %r", apdu)

        assert apdu == self.match_apdu

        future = asyncio.Future()
        future.set_result(AbortOther())
        return future


@bacpypes_debugging
class TestReadPropertyAPI:
    @pytest.mark.asyncio
    async def test_read_property_api(self):
        if _debug:
            TestReadPropertyAPI._debug("test_read_property_api")

        # create an application to trap and test the APDU created
        app = MatchApplication(
            ReadPropertyRequest(
                destination=Address("1.2.3.4"),
                objectIdentifier=ObjectIdentifier("device,1"),
                propertyIdentifier=PropertyIdentifier.localTime,
            )
        )
        await app.read_property("1.2.3.4", "device,1", "local-time")
        await app.read_property("1.2.3.4", "device,1", "57")
        await app.read_property("1.2.3.4", "8,1", "local-time")
        app.close()


@bacpypes_debugging
class TestWritePropertyAPI:
    @pytest.mark.asyncio
    async def test_write_property_unsigned(self):
        if _debug:
            TestWritePropertyAPI._debug("test_write_property_unsigned")

        # create an application to trap and test the APDU created
        app = MatchApplication(
            WritePropertyRequest(
                destination=Address("1.2.3.4"),
                objectIdentifier=ObjectIdentifier("device,1"),
                propertyIdentifier=PropertyIdentifier.vendorIdentifier,
                propertyValue=Unsigned(888),
            )
        )
        await app.write_property("1.2.3.4", "device,1", "vendor-identifier", "888")
        app.close()

    @pytest.mark.asyncio
    async def test_write_property_enumerated(self):
        if _debug:
            TestWritePropertyAPI._debug("test_write_property_enumerated")

        # create an application to trap and test the APDU created
        app = MatchApplication(
            WritePropertyRequest(
                destination=Address("1.2.3.4"),
                objectIdentifier=ObjectIdentifier("device,1"),
                propertyIdentifier=PropertyIdentifier.systemStatus,
                propertyValue=DeviceStatus("operational"),
            )
        )
        await app.write_property("1.2.3.4", "device,1", "system-status", "operational")
        app.close()


@bacpypes_debugging
class TestReadPropertyMultipleAPI:
    @pytest.mark.asyncio
    async def test_read_property_multiple_api(self):
        if _debug:
            TestReadPropertyMultipleAPI._debug("test_read_property_multiple_api")

        # create an application to trap and test the APDU created
        app = MatchApplication(
            ReadPropertyMultipleRequest(
                destination=Address("1.2.3.4"),
                listOfReadAccessSpecs=[
                    ReadAccessSpecification(
                        objectIdentifier=ObjectIdentifier("device,1"),
                        listOfPropertyReferences=[
                            PropertyIdentifier.localDate,
                            PropertyIdentifier.localTime,
                        ],
                    )
                ],
            )
        )
        await app.read_property_multiple(
            "1.2.3.4", ("device,1", ("local-date", "local-time"))
        )
        app.close()