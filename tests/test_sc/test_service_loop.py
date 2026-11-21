import asyncio
import contextlib

import pytest

from bacpypes3.debugging import ModuleLogger

sc_service = pytest.importorskip("bacpypes3.sc.service")
WebSocketClient = sc_service.WebSocketClient
WebSocketServer = sc_service.WebSocketServer

_debug = 0
_log = ModuleLogger(globals())


class FakeSwitch:
    def __init__(self) -> None:
        self.received = []

    async def confirmation(self, pdu) -> None:
        self.received.append(pdu)


class FakeConnection:
    def __init__(self) -> None:
        self.sent = []
        self.closed = False

    async def recv(self) -> bytes:
        await asyncio.Event().wait()
        return b""

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True


async def test_server_loop_waits_then_stops() -> None:
    connection = FakeConnection()
    server = WebSocketServer(FakeSwitch(), connection, "/")

    await asyncio.sleep(0.05)
    assert not server.websocket_task.done()

    await server.outgoing.put(b"\x01\x02")
    await asyncio.sleep(0.05)
    assert connection.sent == [b"\x01\x02"]
    assert not server.websocket_task.done()

    await server.outgoing.put(None)
    await asyncio.wait_for(server.websocket_task, timeout=1.0)
    assert server.websocket_task.exception() is None
    assert connection.closed


async def test_server_loop_stops_on_stop_event() -> None:
    connection = FakeConnection()
    server = WebSocketServer(FakeSwitch(), connection, "/")

    await asyncio.sleep(0.05)
    server.stop.set()
    await asyncio.wait_for(server.websocket_task, timeout=1.0)
    assert server.websocket_task.exception() is None
    assert connection.closed


async def test_client_loop_waits_then_closes(monkeypatch) -> None:
    connection = FakeConnection()

    @contextlib.asynccontextmanager
    async def fake_connect(uri, **kwargs):
        yield connection

    monkeypatch.setattr(sc_service.websockets, "connect", fake_connect)

    client = WebSocketClient(FakeSwitch(), "ws://example.invalid/")

    await asyncio.sleep(0.05)
    assert not client.client_task.done()

    await client.outgoing.put(b"\x03\x04")
    await asyncio.sleep(0.05)
    assert connection.sent == [b"\x03\x04"]
    assert not client.client_task.done()

    await asyncio.wait_for(client.close(), timeout=1.0)
    await asyncio.wait_for(client.client_task, timeout=1.0)
    assert client.client_task.exception() is None
    assert client.eof.is_set()
