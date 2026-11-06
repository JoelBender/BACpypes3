"""Custom sockets belong to the local endpoint, never to two transports."""

import asyncio
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bacpypes3 import ipv4
from bacpypes3.ipv4.app import NormalApplication
from bacpypes3.object import DeviceObject
from bacpypes3.pdu import IPv4Address, LocalBroadcast


@pytest.mark.parametrize("platform", ["posix", "nt"])
@pytest.mark.parametrize("supplied_socket", [False, True])
@pytest.mark.parametrize(
    "address_text",
    ["192.0.2.1:0", "192.0.2.1:47808", "192.0.2.1/24:47808"],
    ids=["ephemeral", "host", "subnet"],
)
async def test_normal_application_socket_ownership(
    monkeypatch, platform, supplied_socket, address_text
):
    """Exercise the application down to asyncio without binding real interfaces."""
    # Patch only the IPv4 module's platform view, not the process-wide os.name.
    monkeypatch.setattr(ipv4, "os", SimpleNamespace(name=platform))
    address = IPv4Address(address_text)
    caller_socket = Mock(spec=socket.socket) if supplied_socket else None
    if caller_socket is not None:
        caller_socket.getsockname.return_value = address.addrTuple

    endpoints = []

    async def create_endpoint(factory, **kwargs):
        endpoint_socket = kwargs.get("sock")
        if endpoint_socket is None:
            endpoint_socket = Mock(spec=socket.socket)
            endpoint_socket.getsockname.return_value = kwargs["local_addr"]

        # asyncio takes ownership of a socket; a second transport is invalid.
        assert all(endpoint_socket is not sock for sock, _, _ in endpoints)
        transport = Mock(spec=asyncio.DatagramTransport)
        transport.get_extra_info.return_value = endpoint_socket
        protocol = factory()
        protocol.connection_made(transport)
        endpoints.append((endpoint_socket, transport, kwargs))
        return transport, protocol

    monkeypatch.setattr(
        asyncio.get_running_loop(), "create_datagram_endpoint", create_endpoint
    )
    app = NormalApplication(
        DeviceObject(objectIdentifier=("device", 1), objectName="socket-test"),
        address,
        bind_socket=caller_socket,
    )
    server = app.normal.server
    try:
        await asyncio.gather(*server._transport_tasks)
        assert server.local_transport is endpoints[0][1]
        assert server._local_transport_ready.is_set()
        if supplied_socket:
            assert endpoints[0][0] is caller_socket
            assert endpoints[0][2] == {"sock": caller_socket}
        else:
            assert endpoints[0][2] == {
                "local_addr": address.addrTuple,
                "allow_broadcast": True,
                "reuse_port": platform != "nt",
            }

        if platform == "nt":
            assert len(endpoints) == 1
            assert server.broadcast_transport is server.local_transport
        elif address_text == "192.0.2.1/24:47808":
            assert len(endpoints) == 2
            assert server.broadcast_transport is endpoints[1][1]
            assert endpoints[1][2] == {
                "local_addr": address.addrBroadcastTuple,
                "allow_broadcast": True,
                "reuse_port": True,
            }
            assert isinstance(server.broadcast_protocol.destination, LocalBroadcast)
        else:
            assert len(endpoints) == 1
            assert server.broadcast_transport is None
    finally:
        app.close()

    for _, transport, _ in endpoints:
        transport.close.assert_called()
