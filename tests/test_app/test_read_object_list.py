#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test read_object_list() API
---------------------------
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

from bacpypes3 import mcp
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier, Unsigned
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.constructeddata import Any, ArrayOf
from bacpypes3.apdu import (
    APDU,
    AbortPDU,
    AbortReason,
    Error,
    ReadPropertyACK,
    ReadPropertyRequest,
)
from bacpypes3.app import Application

# some debugging
_debug = 0
_log = ModuleLogger(globals())

DEVICE = ObjectIdentifier("device,7780")
ADDRESS = Address("1.2.3.4")


@bacpypes_debugging
class ObjectListApplication(Application):
    """
    Instances of this class answer ReadProperty requests for the object-list
    of a single device, optionally aborting the whole-array read the way a
    device that does not segment would.
    """

    def __init__(
        self,
        object_list: List[ObjectIdentifier],
        whole_abort: Optional[str] = None,
        whole_error: Optional[BaseException] = None,
        element_error: Optional[BaseException] = None,
        return_abort: bool = False,
        *args,
        **kwds,
    ):
        if _debug:
            ObjectListApplication._debug("__init__ %r", object_list)
        super().__init__(*args, **kwds)

        self.object_list = object_list
        self.whole_abort = whole_abort
        self.whole_error = whole_error
        self.element_error = element_error
        self.return_abort = return_abort

        self.requests: List[Optional[int]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    def request(self, apdu: APDU) -> asyncio.Future:
        if _debug:
            ObjectListApplication._debug("request %r", apdu)
        assert isinstance(apdu, ReadPropertyRequest)
        assert apdu.pduDestination == ADDRESS
        assert apdu.objectIdentifier == DEVICE
        assert apdu.propertyIdentifier == PropertyIdentifier.objectList

        array_index = apdu.propertyArrayIndex
        self.requests.append(array_index)

        future: asyncio.Future = asyncio.Future()
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        asyncio.ensure_future(self._respond(apdu, array_index, future))
        return future

    async def _respond(
        self, apdu: ReadPropertyRequest, array_index: Optional[int], future
    ) -> None:
        # let other requests get in flight before this one completes
        for _ in range(3):
            await asyncio.sleep(0)
        self.in_flight -= 1

        if array_index is None:
            if self.whole_abort is not None:
                abort = AbortPDU(reason=self.whole_abort)
                if self.return_abort:
                    # read_property() passes a returned abort back as its value
                    future.set_result(abort)
                else:
                    future.set_exception(abort)
                return
            if self.whole_error is not None:
                future.set_exception(self.whole_error)
                return
            value = ArrayOf(ObjectIdentifier)(self.object_list)
        elif array_index == 0:
            value = Unsigned(len(self.object_list))
        else:
            if self.element_error is not None and array_index == 2:
                future.set_exception(self.element_error)
                return
            value = self.object_list[array_index - 1]

        future.set_result(
            ReadPropertyACK(
                objectIdentifier=apdu.objectIdentifier,
                propertyIdentifier=apdu.propertyIdentifier,
                propertyArrayIndex=array_index,
                propertyValue=Any(value),
            )
        )


def make_object_list(count: int) -> List[ObjectIdentifier]:
    return [DEVICE] + [ObjectIdentifier(("analog-value", i)) for i in range(count - 1)]


@bacpypes_debugging
class TestReadObjectList:
    async def test_whole_read(self):
        """The whole array is returned without falling back."""
        object_list = make_object_list(5)
        app = ObjectListApplication(object_list)
        try:
            result = await app.read_object_list("1.2.3.4", "device,7780")
            assert result == object_list
            assert app.requests == [None]
        finally:
            app.close()

    @pytest.mark.parametrize(
        "reason", ["buffer-overflow", "segmentation-not-supported"]
    )
    async def test_fallback(self, reason):
        """The elements are read one at a time and returned in order."""
        object_list = make_object_list(10)
        app = ObjectListApplication(object_list, whole_abort=reason)
        try:
            result = await app.read_object_list(ADDRESS, DEVICE)
            assert result == object_list
            assert app.requests[:2] == [None, 0]
            assert sorted(app.requests[2:]) == list(range(1, 11))
        finally:
            app.close()

    async def test_fallback_returned_abort(self):
        """An abort returned (rather than raised) also falls back."""
        object_list = make_object_list(3)
        app = ObjectListApplication(
            object_list, whole_abort="buffer-overflow", return_abort=True
        )
        try:
            assert await app.read_object_list(ADDRESS, DEVICE) == object_list
            assert app.requests == [None, 0, 1, 2, 3]
        finally:
            app.close()

    async def test_fallback_empty(self):
        """A device with an empty list makes no element requests."""
        app = ObjectListApplication([], whole_abort="buffer-overflow")
        try:
            assert await app.read_object_list(ADDRESS, DEVICE) == []
            assert app.requests == [None, 0]
        finally:
            app.close()

    @pytest.mark.parametrize("concurrency", [1, 3])
    async def test_concurrency_bound(self, concurrency):
        """No more than `concurrency` element reads are in flight."""
        object_list = make_object_list(12)
        app = ObjectListApplication(object_list, whole_abort="buffer-overflow")
        try:
            result = await app.read_object_list(
                ADDRESS, DEVICE, concurrency=concurrency
            )
            assert result == object_list
            assert app.max_in_flight == concurrency
        finally:
            app.close()

    async def test_other_abort_propagates(self):
        """An abort for another reason is raised, not masked."""
        app = ObjectListApplication(make_object_list(3), whole_abort="other")
        try:
            with pytest.raises(AbortPDU) as exc_info:
                await app.read_object_list(ADDRESS, DEVICE)
            assert exc_info.value.apduAbortRejectReason == AbortReason.other
            assert app.requests == [None]
        finally:
            app.close()

    async def test_error_propagates(self):
        """An error response is raised, not masked."""
        error = Error(
            service_choice=ReadPropertyRequest.service_choice,
            errorClass="object",
            errorCode="unknownObject",
        )
        app = ObjectListApplication(make_object_list(3), whole_error=error)
        try:
            with pytest.raises(Error):
                await app.read_object_list(ADDRESS, DEVICE)
            assert app.requests == [None]
        finally:
            app.close()

    async def test_element_error_propagates(self):
        """An error reading one element is raised."""
        app = ObjectListApplication(
            make_object_list(6),
            whole_abort="buffer-overflow",
            element_error=AbortPDU(reason="tsmTimeout"),
        )
        try:
            with pytest.raises(AbortPDU) as exc_info:
                await app.read_object_list(ADDRESS, DEVICE)
            assert exc_info.value.apduAbortRejectReason == AbortReason.tsmTimeout
        finally:
            app.close()

    async def test_invalid_concurrency(self):
        app = ObjectListApplication([])
        try:
            with pytest.raises(ValueError):
                await app.read_object_list(ADDRESS, DEVICE, concurrency=0)
        finally:
            app.close()


@bacpypes_debugging
class TestReadObjectListMCP:
    def test_registered(self):
        assert mcp.read_object_list in mcp.TOOLS

    async def test_tool_fallback(self):
        object_list = make_object_list(4)
        app = ObjectListApplication(object_list, whole_abort="buffer-overflow")
        mcp.set_application(app)
        try:
            result = await mcp.read_object_list("1.2.3.4", "device,7780")
            assert result == {
                "deviceIdentifier": "device,7780",
                "count": 4,
                "objectList": [
                    "device,7780",
                    "analog-value,0",
                    "analog-value,1",
                    "analog-value,2",
                ],
            }
        finally:
            mcp._application = None
            app.close()

    async def test_tool_error(self):
        app = ObjectListApplication(make_object_list(2), whole_abort="other")
        mcp.set_application(app)
        try:
            result = await mcp.read_object_list("1.2.3.4", "device,7780")
            assert result["deviceIdentifier"] == "device,7780"
            assert result["type"] == "AbortPDU"
            assert "objectList" not in result
        finally:
            mcp._application = None
            app.close()
