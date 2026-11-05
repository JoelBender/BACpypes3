#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Loopback self-addressed indication
----------------------------------

`IPv4DatagramServer.indication()` short-circuits a self-addressed
unicast up the stack instead of putting it on the wire, so it isn't
eaten by the anti-reflection drop in `confirmation()` (which stays in
place to guard BBMD re-broadcasts).

Two shapes count as self-addressed on this server's port:

1. an exact match on the server's bound `local_address`, and
2. any 127.x.x.x host on the same port (operator-obvious loopback).

Non-self destinations still call `sendto`; 127/8 traffic on a
*different* port is unrelated and stays on the wire.

The tests bypass ``IPv4DatagramServer.__init__`` (which would try to
open a real socket) and construct an instance directly with the fields
``indication`` reads, plus a fake transport that records ``sendto``
calls and a stub upstream server that captures ``response(pdu)``.
"""

from typing import Any, List, Tuple

import pytest

from bacpypes3.comm import Client, bind
from bacpypes3.ipv4 import IPv4DatagramServer
from bacpypes3.pdu import IPv4Address, PDU


class FakeTransport:
    """Records every ``sendto`` call so tests can assert wire activity."""

    def __init__(self) -> None:
        self.sent: List[Tuple[bytes, Tuple[str, int]]] = []

    def sendto(self, data: bytes, addr: Tuple[str, int]) -> None:
        self.sent.append((data, addr))


class CapturingUpstream(Client[PDU]):
    """Captures every PDU handed up via ``response()``.

    ``IPv4DatagramServer.response(pdu)`` calls
    ``self.serverPeer.confirmation(pdu)`` — its serverPeer is a
    ``Client``, so this stub is a Client whose ``confirmation`` records
    what came up.
    """

    def __init__(self) -> None:
        super().__init__()
        self.received: List[PDU] = []

    async def confirmation(self, pdu: PDU) -> None:  # type: ignore[override]
        self.received.append(pdu)


def _make_server(local_address: Tuple[str, int]) -> Tuple[
    IPv4DatagramServer, FakeTransport, CapturingUpstream
]:
    """Build an IPv4DatagramServer without touching the network."""
    import asyncio

    server = IPv4DatagramServer.__new__(IPv4DatagramServer)
    server.local_address = local_address
    server.local_transport = FakeTransport()  # type: ignore[assignment]
    server.local_protocol = None
    server.broadcast_address = (local_address[0], local_address[1])
    server.broadcast_transport = None
    server.broadcast_protocol = None
    server._transport_tasks = []
    server._local_transport_ready = asyncio.Event()
    server._local_transport_ready.set()

    upstream = CapturingUpstream()
    bind(upstream, server)
    return server, server.local_transport, upstream  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_indication_self_bound_address_loops_back() -> None:
    """Destination == self.local_address is delivered in-process, not on the wire."""
    server, transport, upstream = _make_server(("10.0.0.5", 47808))

    await server.indication(
        PDU(b"hello-self", destination=IPv4Address(("10.0.0.5", 47808)))
    )

    assert transport.sent == []
    assert len(upstream.received) == 1
    assert upstream.received[0].pduData == b"hello-self"
    assert isinstance(upstream.received[0].pduSource, IPv4Address)
    assert upstream.received[0].pduSource.addrTuple == ("10.0.0.5", 47808)


@pytest.mark.asyncio
async def test_indication_loopback_127_same_port_loops_back() -> None:
    """127.x.x.x on the same port hits the loopback shortcut."""
    server, transport, upstream = _make_server(("10.0.0.5", 47808))

    await server.indication(
        PDU(b"hello-loopback", destination=IPv4Address(("127.0.0.1", 47808)))
    )

    assert transport.sent == []
    assert len(upstream.received) == 1
    assert upstream.received[0].pduData == b"hello-loopback"


@pytest.mark.asyncio
async def test_indication_non_self_goes_on_the_wire() -> None:
    """Non-self, non-loopback destinations still call sendto()."""
    server, transport, upstream = _make_server(("10.0.0.5", 47808))

    await server.indication(
        PDU(b"hello-remote", destination=IPv4Address(("10.0.0.99", 47808)))
    )

    assert transport.sent == [(b"hello-remote", ("10.0.0.99", 47808))]
    assert upstream.received == []


@pytest.mark.asyncio
async def test_indication_loopback_different_port_goes_on_the_wire() -> None:
    """127.x.x.x on a *different* port is unrelated traffic; do not shortcut."""
    server, transport, upstream = _make_server(("10.0.0.5", 47808))

    await server.indication(
        PDU(b"hello-otherport", destination=IPv4Address(("127.0.0.1", 47809)))
    )

    assert transport.sent == [(b"hello-otherport", ("127.0.0.1", 47809))]
    assert upstream.received == []
