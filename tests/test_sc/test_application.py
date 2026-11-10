"""
Test BACnet/SC Application Wiring
---------------------------------

A secure-connect Network Port object added to an Application builds an
SCNodeLinkLayer.  The VMAC and device UUID must be stable, so generated values
are written back to the objects, and a new VMAC after a collision updates the
network port and the network adapter.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import pytest

from bacpypes3.app import Application
from bacpypes3.debugging import ModuleLogger
from bacpypes3.local.device import DeviceObject
from bacpypes3.local.networkport import NetworkPortObject
from bacpypes3.pdu import SecureConnectAddress
from bacpypes3.sc.link import SCNodeLinkLayer

# some debugging
_debug = 0
_log = ModuleLogger(globals())

VMAC = SecureConnectAddress(b"\x12\x34\x56\x78\x9a\xbc")
DEVICE_UUID = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")


@pytest.fixture(autouse=True)
def no_hub_connection(monkeypatch):
    """Build the link layer but don't start connecting to the hub."""
    monkeypatch.setattr(SCNodeLinkLayer, "start", lambda self: None)


def make_device(**kwargs) -> DeviceObject:
    return DeviceObject(
        objectIdentifier=("device", 1),
        objectName="dev",
        vendorIdentifier=999,
        **kwargs,
    )


def make_port(*args, **kwargs) -> NetworkPortObject:
    port = NetworkPortObject(
        *args,
        objectIdentifier=("network-port", 1),
        objectName="sc",
        scPrimaryHubUri="wss://hub.example.org/",
        **kwargs,
    )
    port._ssl_context = object()
    return port


async def test_configured_vmac_and_uuid(caplog):
    port = make_port(VMAC)
    with caplog.at_level(logging.WARNING):
        app = Application.from_object_list(
            [make_device(deviceUUID=DEVICE_UUID.bytes), port]
        )
    assert not caplog.records

    link_layer = app.link_layers[port.objectIdentifier]
    assert isinstance(link_layer, SCNodeLinkLayer)
    assert link_layer.local_vmac == VMAC
    assert link_layer.connector.device_uuid == DEVICE_UUID
    assert app.nsap.local_adapter.adapterAddr == VMAC

    app.close()


async def test_generated_vmac_and_uuid_written_back(caplog):
    device = make_device()

    # a port with no VMAC, as if it was left out of the configuration
    port = make_port(VMAC)
    object.__setattr__(port, "macAddress", None)
    assert not port.macAddress

    with caplog.at_level(logging.WARNING):
        app = Application.from_object_list([device, port])
    messages = [record.getMessage() for record in caplog.records]
    assert any("no macAddress" in message for message in messages)
    assert any("no deviceUUID" in message for message in messages)

    link_layer = app.link_layers[port.objectIdentifier]

    # the generated values are on the objects so they can be saved
    assert bytes(port.macAddress) == link_layer.local_vmac.addrAddr
    assert bytes(port.macAddress)[0] & 0x0F == 0x02
    assert uuid.UUID(bytes=bytes(device.deviceUUID)) == link_layer.connector.device_uuid

    app.close()


async def test_device_object_first():
    # from_object_list() finds the device object first, add_object() doesn't
    app = Application()
    with pytest.raises(RuntimeError, match="device object"):
        app.add_object(make_port(VMAC))
    app.close()


async def test_vmac_change_updates_port_and_adapter():
    port = make_port(VMAC)
    app = Application.from_object_list(
        [make_device(deviceUUID=DEVICE_UUID.bytes), port]
    )
    link_layer = app.link_layers[port.objectIdentifier]

    # the connector picked a new VMAC after a collision
    new_vmac = SecureConnectAddress(b"\x22\x00\x00\x00\x00\x01")
    link_layer.connector.on_vmac_change(new_vmac)

    assert link_layer.local_vmac == new_vmac
    assert bytes(port.macAddress) == new_vmac.addrAddr
    assert app.nsap.local_adapter.adapterAddr == new_vmac

    app.close()


async def test_async_close_runs(monkeypatch):
    closed = []

    async def close(self):
        closed.append(self)

    monkeypatch.setattr(SCNodeLinkLayer, "close", close)

    port = make_port(VMAC)
    app = Application.from_object_list(
        [make_device(deviceUUID=DEVICE_UUID.bytes), port]
    )
    link_layer = app.link_layers[port.objectIdentifier]

    # deleting the port closes its link layer
    app.delete_object(port)
    assert port.objectIdentifier not in app.link_layers
    assert len(app._closing_tasks) == 1

    # the task runs, then its done callback forgets it
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert closed == [link_layer]
    assert not app._closing_tasks

    # so does closing the application
    port = make_port(VMAC)
    app = Application.from_object_list(
        [make_device(deviceUUID=DEVICE_UUID.bytes), port]
    )
    link_layer = app.link_layers[port.objectIdentifier]
    app.close()
    await asyncio.sleep(0)
    assert closed[-1] is link_layer
