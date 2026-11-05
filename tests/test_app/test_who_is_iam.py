#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Who-Is / I-Am race conditions
-----------------------------------

Regression tests for two related bugs triggered when more than one I-Am
is processed for the same pending Who-Is before the event loop has a
chance to run the WhoIsFuture's "done" callback:

1. WhoIsFuture.match() / who_is_timeout() call ``future.set_result()``
   without checking whether the future is already done, so a duplicate,
   retransmitted, or simply a second I-Am arriving for an
   already-resolved Who-Is raises ``asyncio.InvalidStateError``. This is
   easy to trigger on any network where more than one device answers a
   Who-Is close together (all devices behind one router/gateway address,
   or a busy segment with many devices), and gets *more* likely to fire
   the more devices are on the network, not less.

2. Application.indication()'s generic exception handler unconditionally
   builds an ``Error`` APDU using the offending request as context,
   before checking whether that request was even a confirmed service
   that could receive a response. Building an ``Error`` requires
   ``apduInvokeID``, which unconfirmed requests (such as ``IAmRequest``)
   do not have, so handling *any* exception raised while processing an
   unconfirmed request itself raises ``AttributeError`` and masks the
   original exception.
"""

import asyncio
from typing import Callable, Any

import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.apdu import IAmRequest
from bacpypes3.app import Application

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def _i_am(address: Address, instance: int = 100) -> IAmRequest:
    """Build an I-Am as if it had just arrived from `address`."""
    return IAmRequest(
        iAmDeviceIdentifier=ObjectIdentifier(("device", instance)),
        maxAPDULengthAccepted=1024,
        segmentationSupported="noSegmentation",
        vendorID=999,
        source=address,
    )


@bacpypes_debugging
class TestWhoIsIAmRace:
    _debug: Callable[..., None]

    @pytest.mark.asyncio
    async def test_duplicate_i_am_does_not_crash_matching_who_is(self) -> None:
        """
        Two I-Am responses for the same address, processed back-to-back
        (i.e. before the loop runs the future's done-callback and removes
        it from app._who_is_futures), must not raise InvalidStateError.
        This is the shape of a device that answers twice, or of a Who-Is
        broadcast that many devices reply to close together.
        """
        if _debug:
            TestWhoIsIAmRace._debug("test_duplicate_i_am_does_not_crash_matching_who_is")

        app = Application()
        address = Address("10.0.0.1")

        who_is_future = app.who_is(address=address, timeout=3.0)

        # first I-Am resolves the (only_one=True) future inside match()
        await app.do_IAmRequest(_i_am(address))

        # second I-Am for the same address arrives before the loop has run
        # the future's done-callback (do_IAmRequest never awaits anything
        # that suspends, so this happens synchronously within the test) -
        # this must be handled, not raise
        await app.do_IAmRequest(_i_am(address))

        result = await who_is_future
        assert len(result) == 1

        app.close()

    @pytest.mark.asyncio
    async def test_late_timeout_after_match_does_not_crash(self) -> None:
        """
        If an I-Am resolves the future via match() and the scheduled
        who_is_timeout() callback fires anyway before who_is_done() has
        run (the done-callback is scheduled with call_soon, not run
        synchronously), who_is_timeout() must not raise
        InvalidStateError either.
        """
        if _debug:
            TestWhoIsIAmRace._debug("test_late_timeout_after_match_does_not_crash")

        app = Application()
        address = Address("10.0.0.2")

        who_is_future = app.who_is(address=address, timeout=3.0)
        assert len(app._who_is_futures) == 1
        pending = app._who_is_futures[0]

        await app.do_IAmRequest(_i_am(address))
        assert pending.future.done()

        # simulate the scheduled timeout firing before the done-callback
        # has had a chance to run and cancel it
        pending.who_is_timeout()

        result = await who_is_future
        assert len(result) == 1

        app.close()

    @pytest.mark.asyncio
    async def test_broadcast_who_is_survives_many_replies(self) -> None:
        """
        A global (not only_one) Who-Is that collects many I-Ams must
        still work, and a duplicate reply for a device already recorded
        must not crash the collection.
        """
        if _debug:
            TestWhoIsIAmRace._debug("test_broadcast_who_is_survives_many_replies")

        app = Application()
        who_is_future = app.who_is(timeout=3.0)

        addresses = [Address(f"10.0.0.{i}") for i in range(1, 9)]
        for i, addr in enumerate(addresses):
            await app.do_IAmRequest(_i_am(addr, instance=100 + i))
        # a duplicate/retransmitted reply for one already-seen device
        await app.do_IAmRequest(_i_am(addresses[0], instance=100))

        pending = app._who_is_futures[0]
        pending.who_is_timeout()

        result = await who_is_future
        assert len(result) == len(addresses)

        app.close()

    @pytest.mark.asyncio
    async def test_exception_handling_unconfirmed_request_does_not_crash(self) -> None:
        """
        An exception raised while processing an *unconfirmed* request
        (I-Am has no do_IAmRequest failure path in normal use, but any
        unconfirmed request handler can raise - e.g. exactly the
        InvalidStateError from the two tests above, before they were
        fixed) must be logged, not turned into a second crash while
        Application.indication() tries to build an Error APDU that
        requires a confirmed request's apduInvokeID.
        """
        if _debug:
            TestWhoIsIAmRace._debug(
                "test_exception_handling_unconfirmed_request_does_not_crash"
            )

        app = Application()
        address = Address("10.0.0.3")

        async def do_IAmRequest_raises(apdu: Any) -> None:
            raise RuntimeError("simulated failure handling an unconfirmed request")

        app.do_IAmRequest = do_IAmRequest_raises  # type: ignore[method-assign]

        # must not raise AttributeError building an Error() for a request
        # with no apduInvokeID - the exception is logged and swallowed,
        # exactly as it already is for any other unconfirmed request
        await app.indication(_i_am(address))

        app.close()
