#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BBMD Annex U regressions
------------------------

ANSI/ASHRAE 135-2024 Annex U pins down five BBMD/foreign-device behaviors
that used to be wrong or missing in ``bacpypes3.ipv6.service.BIPBBMD``:

* U.4.4 — a *Forwarded-Address-Resolution* received from a peer must be
  re-emitted (local broadcast + fan-out to registered foreign devices)
  with its original source-virtual-address / source-IPv6 fields intact.
* U.4.4 — a *Distribute-Broadcast-to-Network* received from an address
  that is **not** in the FDT must be answered with a NAK Result
  (``0x00C0``), not silently dropped.
* U.4.5.5 — a foreign-device registration must survive its requested
  TTL plus a 30-second grace window before the FDT entry is purged.
* U.4.5.4 — deleting an FDT entry that isn't present must be reported
  with the IPv6-specific NAK ``0x00A0`` (not the IPv4 ``0x0050``).
* U.5    — the on-the-wire *Virtual-Address-Resolution-ACK* must decode
  into a ``VirtualAddressResolutionACK`` LPDU so ``BIPBBMD.confirmation``
  dispatches it as a resolution response instead of as a plain
  address-resolution ACK.

These tests build a ``BIPBBMD`` with a virtual address, cancel its own
FDT clock (we drive ``fdt_clock`` manually), and wire it through a real
``BVLLCodec`` to a ``Sink`` server that records every encoded outbound
frame. The one codec-dispatch case uses a separate stack (a
``Receiver`` client behind a fresh ``BVLLCodec``) to prove that the
decoder maps the ACK to the right LPDU class.
"""

from typing import List, Tuple

import pytest

from bacpypes3.comm import Client, Server, bind
from bacpypes3.pdu import PDU, IPv6Address, VirtualAddress
from bacpypes3.ipv6.bvll import (
    BVLLCodec,
    LPCI,
    DeleteForeignDeviceTableEntry,
    DistributeBroadcastToNetwork,
    ForwardedAddressResolution,
    VirtualAddressResolutionACK,
)
from bacpypes3.ipv6.service import BIPBBMD


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class Sink(Server[PDU]):
    """Records every encoded frame the BBMD hands downstream."""

    def __init__(self) -> None:
        super().__init__()
        self.frames: List[Tuple[object, bytes]] = []

    async def indication(self, pdu: PDU) -> None:  # type: ignore[override]
        self.frames.append((pdu.pduDestination, bytes(pdu.pduData)))


class Receiver(Client[PDU]):
    """Captures decoded LPDUs handed up by a codec."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: List[PDU] = []

    async def confirmation(self, pdu: PDU) -> None:  # type: ignore[override]
        self.messages.append(pdu)


LOCAL = IPv6Address("[fd77:3:b::10]")
PEER = IPv6Address("[fd77:3:a::10]")
FOREIGN = IPv6Address("[fd77:3:a::20]:47809")
VM = VirtualAddress(bytes.fromhex("010203"))
TARGET = VirtualAddress(bytes.fromhex("070809"))


@pytest.fixture
async def bbmd_stack():
    """Build a ``BIPBBMD -> BVLLCodec -> Sink`` stack with the FDT clock stopped.

    Async so ``BIPBBMD.__init__`` — which schedules its FDT clock via
    ``asyncio.get_event_loop().call_soon(...)`` — sees the running loop
    pytest-asyncio has already installed for the test.
    """
    bbmd = BIPBBMD(LOCAL, virtual_address=VM)
    bbmd._fdt_clock_handle.cancel()
    bbmd.add_peer(PEER)

    codec = BVLLCodec()
    sink = Sink()
    bind(bbmd, codec, sink)

    try:
        yield bbmd, codec, sink
    finally:
        bbmd._fdt_clock_handle.cancel()


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


async def test_u44_forwarded_resolution_preserves_origin_and_fans_out(bbmd_stack) -> None:
    """A peer's Forwarded-Address-Resolution is rebroadcast locally and to every FDT entry,
    with the original source-virtual-address / source-IPv6 fields left untouched."""
    bbmd, codec, sink = bbmd_stack
    bbmd.register_foreign_device(FOREIGN, 60)

    msg = ForwardedAddressResolution(VM, TARGET, PEER, source=PEER)
    await codec.confirmation(msg.encode())

    assert len(sink.frames) == 2
    assert str(sink.frames[0][0]) == "*"          # local broadcast first
    assert sink.frames[1][0] == FOREIGN           # then the foreign device

    for _dest, data in sink.frames:
        packet = PDU(data)
        LPCI.decode(packet)
        decoded = ForwardedAddressResolution.decode(packet)
        assert decoded.bvlciTargetVirtualAddress == TARGET
        assert decoded.bvlciOriginalSourceIPv6Address == PEER


async def test_u44_unregistered_distribution_returns_ipv6_nak(bbmd_stack) -> None:
    """A DBTN from a non-registered address earns a 0x00C0 NAK, not a silent drop."""
    _bbmd, codec, sink = bbmd_stack

    dbtn = DistributeBroadcastToNetwork(VM, b"\x01\x00\x10\x08", source=FOREIGN)
    await codec.confirmation(dbtn.encode())

    assert len(sink.frames) == 1
    assert sink.frames[0][0] == FOREIGN
    assert sink.frames[0][1][-2:] == bytes.fromhex("00c0")


async def test_u455_registration_grace_and_renewal(bbmd_stack) -> None:
    """A 2-second registration is retained for TTL+30s and renews on re-registration."""
    bbmd, _codec, _sink = bbmd_stack

    # initial registration: TTL 2 + 30s grace => fdRemain == 32
    bbmd.register_foreign_device(FOREIGN, 2)
    assert bbmd.bbmdFDT[0].fdRemain == 32

    # 10 ticks in: still present, well inside the grace window
    for _ in range(10):
        bbmd.fdt_clock()
        bbmd._fdt_clock_handle.cancel()
    assert len(bbmd.bbmdFDT) == 1

    # re-registration resets fdRemain back to 32
    bbmd.register_foreign_device(FOREIGN, 2)
    assert bbmd.bbmdFDT[0].fdRemain == 32

    # 32 ticks later: the entry has aged out
    for _ in range(32):
        bbmd.fdt_clock()
        bbmd._fdt_clock_handle.cancel()
    assert bbmd.bbmdFDT == []


async def test_u454_delete_existing_and_missing(bbmd_stack) -> None:
    """Deleting a live FDT entry returns 0x0000; deleting a missing one returns 0x00A0."""
    bbmd, codec, sink = bbmd_stack
    bbmd.register_foreign_device(FOREIGN, 2)

    for expected in ("0000", "00a0"):
        sink.frames.clear()
        req = DeleteForeignDeviceTableEntry(VM, FOREIGN, source=PEER)
        await codec.confirmation(req.encode())
        assert len(sink.frames) == 1
        assert sink.frames[0][1][-2:] == bytes.fromhex(expected)


async def test_u5_virtual_resolution_ack_decodes_to_correct_lpdu() -> None:
    """The BVLL codec must build a VirtualAddressResolutionACK (function 7) — not the
    generic AddressResolutionACK — so the BBMD can dispatch it correctly."""
    receiver = Receiver()
    codec = BVLLCodec()
    bind(receiver, codec)

    await codec.confirmation(VirtualAddressResolutionACK(VM, TARGET, source=PEER).encode())

    assert len(receiver.messages) == 1
    assert type(receiver.messages[0]) is VirtualAddressResolutionACK
    assert receiver.messages[0].bvlciFunction == 7
