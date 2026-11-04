"""
Test the bacpypes3.mcp tool functions called directly as a library.

These tests do not need the optional ``mcp`` SDK.
"""

import sys

import pytest

from bacpypes3 import mcp as bacpypes_mcp
from bacpypes3.pdu import Address

from .conftest import DEVICE_ADDRESS, DEVICE_INSTANCE


class TestApplicationInjection:
    def test_get_application_without_app_raises(self, no_application) -> None:
        with pytest.raises(RuntimeError, match="set_application"):
            bacpypes_mcp.get_application()

    async def test_set_application(self, apps) -> None:
        client, _device = apps
        assert bacpypes_mcp.get_application() is client


class TestReadWrite:
    async def test_read_property(self, apps) -> None:
        result = await bacpypes_mcp.read_property(
            DEVICE_ADDRESS, f"device,{DEVICE_INSTANCE}", "object-name"
        )
        assert result == {
            "objectIdentifier": f"device,{DEVICE_INSTANCE}",
            "propertyIdentifier": "object-name",
            "propertyArrayIndex": None,
            "value": "Farragut",
        }

    async def test_read_property_array_index(self, apps) -> None:
        # index 0 of the object list is its length: device + port + point
        result = await bacpypes_mcp.read_property(
            DEVICE_ADDRESS, f"device,{DEVICE_INSTANCE}", "object-list[0]"
        )
        assert result["propertyArrayIndex"] == 0
        assert result["value"] == 3

    async def test_read_property_unknown_object(self, apps) -> None:
        result = await bacpypes_mcp.read_property(
            DEVICE_ADDRESS, "analog-value,99", "present-value"
        )
        assert "value" not in result
        assert result["errorClass"] == "object"
        assert result["errorCode"] == "unknown-object"

    async def test_write_then_read(self, apps) -> None:
        result = await bacpypes_mcp.write_property(
            DEVICE_ADDRESS, "analog-value,1", "present-value", 42.0
        )
        assert result == {"ok": True}

        result = await bacpypes_mcp.read_property(
            DEVICE_ADDRESS, "analog-value,1", "present-value"
        )
        assert result["value"] == 42.0

    async def test_write_null_requires_priority(self, apps) -> None:
        with pytest.raises(ValueError, match="priority"):
            await bacpypes_mcp.write_property(
                DEVICE_ADDRESS, "analog-value,1", "present-value", "null"
            )

    async def test_read_property_multiple(self, apps) -> None:
        result = await bacpypes_mcp.read_property_multiple(
            DEVICE_ADDRESS,
            [
                "analog-value,1",
                "present-value",
                "units",
                f"device,{DEVICE_INSTANCE}",
                "object-name",
            ],
        )
        values = {
            (r["objectIdentifier"], r["propertyIdentifier"]): r["value"] for r in result
        }
        assert values == {
            ("analog-value,1", "present-value"): 12.5,
            ("analog-value,1", "units"): "no-units",
            (f"device,{DEVICE_INSTANCE}", "object-name"): "Farragut",
        }


class TestDiscovery:
    async def test_who_is(self, apps) -> None:
        result = await bacpypes_mcp.who_is(low_limit=DEVICE_INSTANCE)
        assert len(result) == 1
        assert result[0]["i-am-device-identifier"] == f"device,{DEVICE_INSTANCE}"
        assert result[0]["pduSource"] == str(Address(DEVICE_ADDRESS))

    async def test_who_has_by_name(self, apps) -> None:
        result = await bacpypes_mcp.who_has(object_name="Some point")
        assert len(result) == 1
        assert result[0]["device-identifier"] == f"device,{DEVICE_INSTANCE}"
        assert result[0]["object-identifier"] == "analog-value,1"
        assert result[0]["pduSource"] == str(Address(DEVICE_ADDRESS))

    async def test_who_has_requires_identifier_or_name(self, apps) -> None:
        with pytest.raises(ValueError):
            await bacpypes_mcp.who_has()


class TestLocal:
    async def test_get_config(self, apps) -> None:
        result = await bacpypes_mcp.get_config()
        assert set(result) == {"BACpypes", "application"}
        object_ids = {obj["object-identifier"] for obj in result["application"]}
        assert object_ids == {"device,998", "network-port,1"}

    async def test_bbmd_tools_require_ipv4(self, apps) -> None:
        with pytest.raises(RuntimeError, match="IPv4 only"):
            await bacpypes_mcp.read_broadcast_distribution_table("192.168.0.1")


class TestBuildServerImportGuard:
    def test_missing_sdk_gives_clear_error(self, monkeypatch) -> None:
        # a None entry in sys.modules makes the import fail, which is what
        # happens with the mcp 1.x SDK (no mcp.server.mcpserver module)
        monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", None)
        with pytest.raises(ImportError, match="version 2 or later"):
            bacpypes_mcp.build_server()
