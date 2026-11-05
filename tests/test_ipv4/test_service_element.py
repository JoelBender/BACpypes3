"""Check BVLL reply matching and request cleanup."""

import asyncio

import pytest
import pytest_asyncio

from bacpypes3.comm import ServiceAccessPoint, bind
from bacpypes3.ipv4.bvll import (
    FDTEntry,
    ReadBroadcastDistributionTableAck,
    ReadForeignDeviceTableAck,
    Result,
)
from bacpypes3.ipv4.service import BVLLServiceElement
from bacpypes3.pdu import IPv4Address

from ..clocked_test import ClockedTest


PEER = IPv4Address("192.0.2.1")
OTHER = IPv4Address("192.0.2.2")
KINDS = ("read_bdt", "read_fdt", "write_bdt")


class Sink(ServiceAccessPoint):
    async def sap_indication(self, pdu):
        pass


@pytest_asyncio.fixture
async def service():
    element = BVLLServiceElement()
    bind(element, Sink())
    loop = asyncio.get_running_loop()
    errors = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda loop, context: errors.append(context))
    try:
        yield element
    finally:
        for kind in KINDS:
            handle = getattr(element, kind + "_timeout_handle")
            if handle is not None:
                handle.cancel()
            future = getattr(element, kind + "_future")
            if future is not None:
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()
        await asyncio.sleep(0)
        loop.set_exception_handler(previous_handler)
    assert errors == []


def start(element, kind, address=PEER, timeout=1.0):
    if kind == "read_bdt":
        return element.read_broadcast_distribution_table(address, timeout)
    if kind == "read_fdt":
        return element.read_foreign_device_table(address, timeout)
    return element.write_broadcast_distribution_table(address, [], timeout)


def reply(kind, source=PEER):
    if kind == "read_bdt":
        return ReadBroadcastDistributionTableAck([OTHER], source=source)
    if kind == "read_fdt":
        entry = FDTEntry()
        entry.fdAddress = OTHER
        entry.fdTTL = 60
        entry.fdRemain = 45
        return ReadForeignDeviceTableAck([entry], source=source)
    return Result(0x0010, source=source)


def check_reply(future, pdu):
    if isinstance(pdu, Result):
        assert future.exception() is pdu
    elif isinstance(pdu, ReadBroadcastDistributionTableAck):
        assert future.result() == pdu.bvlciBDT
    else:
        assert future.result() == pdu.bvlciFDT


def check_clear(element, kind, handle):
    assert handle.cancelled()
    assert getattr(element, kind + "_future") is None
    assert getattr(element, kind + "_timeout_handle") is None
    assert getattr(element, kind + "_address") is None


@pytest.mark.parametrize("kind", KINDS[:2])
async def test_unsolicited_and_repeated_ack(service, kind):
    pdu = reply(kind)
    await service.confirmation(pdu)
    future = start(service, kind)
    handle = getattr(service, kind + "_timeout_handle")
    await service.confirmation(pdu)
    check_reply(future, pdu)
    check_clear(service, kind, handle)
    await service.confirmation(pdu)
    check_reply(future, pdu)


@pytest.mark.parametrize("kind", KINDS[:2])
async def test_ack_source(service, kind):
    future = start(service, kind)
    await service.confirmation(reply(kind, OTHER))
    assert not future.done()
    pdu = reply(kind)
    await service.confirmation(pdu)
    check_reply(future, pdu)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("cancel", [False, True])
async def test_reply_after_timeout_or_cancel(service, kind, cancel):
    with ClockedTest(asyncio.get_running_loop()) as clock:
        future = start(service, kind, timeout=0.25)
        handle = getattr(service, kind + "_timeout_handle")
        if cancel:
            future.cancel()
            # Deliver the reply before the done callback can run.
            await service.confirmation(reply(kind))
        else:
            await clock.advance(0.24)
            assert not future.done()
            await clock.advance(0.01)
            assert future.result() is None
            await service.confirmation(reply(kind))
        await clock.advance(1.0)
        if cancel:
            assert future.cancelled()
        else:
            assert future.result() is None
        check_clear(service, kind, handle)


@pytest.mark.parametrize(
    "kind,code",
    [
        ("read_bdt", 0x0020),
        ("read_fdt", 0x0040),
        ("write_bdt", 0x0010),
        ("write_bdt", 0x0000),
    ],
)
async def test_result_source_and_code(service, kind, code):
    await service.confirmation(Result(code, source=PEER))
    futures = {name: start(service, name) for name in KINDS}
    handle = getattr(service, kind + "_timeout_handle")
    await service.confirmation(Result(code, source=OTHER))
    await service.confirmation(Result(0x0030, source=PEER))
    assert all(not future.done() for future in futures.values())
    pdu = Result(code, source=PEER)
    await service.confirmation(pdu)
    assert futures[kind].exception() is pdu
    check_clear(service, kind, handle)
    await service.confirmation(pdu)
    assert all(not future.done() for name, future in futures.items() if name != kind)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("cancel", [False, True])
async def test_old_callback_keeps_new_request(service, kind, cancel):
    first = start(service, kind)
    handle = getattr(service, kind + "_timeout_handle")
    with pytest.raises(RuntimeError, match="request pending"):
        start(service, kind)
    if cancel:
        first.cancel()
    else:
        pdu = reply(kind)
        await service.confirmation(pdu)
        check_reply(first, pdu)
    second = start(service, kind, OTHER)
    assert handle.cancelled()
    await asyncio.sleep(0)
    assert getattr(service, kind + "_future") is second
    await service.confirmation(reply(kind))
    assert not second.done()
    pdu = reply(kind, OTHER)
    await service.confirmation(pdu)
    check_reply(second, pdu)
