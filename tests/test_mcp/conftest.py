"""
Fixtures for the bacpypes3.mcp tests.

Two Applications share an in-memory VirtualNetwork (the same shape as
samples/ip-to-vlan.py) so the tools exercise the real BACnet stack without
touching a real network:

* ``client`` (device,998, MAC 0x02) is the application the MCP tools drive.
* ``device`` (device,997, MAC 0x03) is the "remote" device the tools talk to.
"""

from __future__ import annotations

import itertools
from typing import Any, AsyncIterator, Iterator

import pytest

from bacpypes3 import mcp as bacpypes_mcp
from bacpypes3.app import Application
from bacpypes3.vlan import VirtualNetwork

CLIENT_ADDRESS = "0x02"
DEVICE_ADDRESS = "0x03"
DEVICE_INSTANCE = 997

# VirtualNetwork names are global and must be unique
_network_counter = itertools.count(1)


def _device_object(instance: int, name: str) -> dict[str, Any]:
    return {
        "apdu-segment-timeout": 1000,
        "apdu-timeout": 3000,
        "application-software-version": "1.0",
        "database-revision": 1,
        "firmware-revision": "N/A",
        "max-apdu-length-accepted": 1024,
        "model-name": "N/A",
        "number-of-apdu-retries": 3,
        "object-identifier": f"device,{instance}",
        "object-name": name,
        "object-type": "device",
        "protocol-revision": 31,
        "protocol-version": 1,
        "segmentation-supported": "segmented-both",
        "system-status": "operational",
        "vendor-identifier": 999,
        "vendor-name": "BACpypes",
    }


def _network_port(network_name: str, mac_address: str) -> dict[str, Any]:
    return {
        "changes-pending": False,
        "mac-address": mac_address,
        "network-interface-name": network_name,
        "network-type": "virtual",
        "object-identifier": "network-port,1",
        "object-name": "NetworkPort-1",
        "object-type": "network-port",
        "out-of-service": False,
        "protocol-level": "bacnet-application",
        "reliability": "no-fault-detected",
    }


def _build_pair(network_name: str) -> tuple[Application, Application]:
    client_objects: list[dict[str, Any]] = [
        _device_object(998, "Exeter"),
        _network_port(network_name, CLIENT_ADDRESS),
    ]
    device_objects: list[dict[str, Any]] = [
        _device_object(DEVICE_INSTANCE, "Farragut"),
        _network_port(network_name, DEVICE_ADDRESS),
        {
            "object-identifier": "analog-value,1",
            "object-name": "Some point",
            "object-type": "analog-value",
            "out-of-service": False,
            "present-value": 12.5,
            "units": "no-units",
        },
    ]
    return (
        Application.from_json(client_objects),
        Application.from_json(device_objects),
    )


@pytest.fixture
async def apps() -> AsyncIterator[tuple[Application, Application]]:
    """
    Build the client/device pair, inject the client into bacpypes3.mcp, and
    tear everything down (including the module-level state) afterwards.
    """
    network_name = f"mcp-test-{next(_network_counter)}"
    VirtualNetwork(network_name)

    client, device = _build_pair(network_name)
    bacpypes_mcp.set_application(client)
    try:
        yield client, device
    finally:
        bacpypes_mcp._application = None
        bacpypes_mcp._bvll_ase = None
        client.close()
        device.close()
        VirtualNetwork._networks.pop(network_name, None)


@pytest.fixture
def no_application() -> Iterator[None]:
    """Ensure no Application is injected for the duration of a test."""
    saved = bacpypes_mcp._application
    bacpypes_mcp._application = None
    try:
        yield
    finally:
        bacpypes_mcp._application = saved
