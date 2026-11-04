"""
Test the bacpypes3.mcp tool functions called directly as a library.

These tests do not need the optional ``mcp`` SDK.
"""

import re
import sys
from typing import Any

import pytest

from bacpypes3 import mcp as bacpypes_mcp
from bacpypes3.errors import AbortOther
from bacpypes3.pdu import Address

from .conftest import DEVICE_ADDRESS, DEVICE_INSTANCE

# result keys use the kebab-case ASN.1 style of sequence_to_json output
_KEBAB_CASE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def assert_kebab_case_keys(value: Any) -> None:
    """Recursively check every dict key in a tool result is kebab-case."""
    if isinstance(value, dict):
        for key, item in value.items():
            assert _KEBAB_CASE.match(key), f"key not kebab-case: {key!r}"
            assert_kebab_case_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_kebab_case_keys(item)


class TestEncodeError:
    def test_abort_keys(self) -> None:
        result = bacpypes_mcp._encode_error(AbortOther())
        assert result["type"] == "AbortOther"
        assert result["abort-reason"] == "other"
        assert_kebab_case_keys(result)


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
            "object-identifier": f"device,{DEVICE_INSTANCE}",
            "property-identifier": "object-name",
            "property-array-index": None,
            "value": "Farragut",
        }

    async def test_read_property_array_index(self, apps) -> None:
        # index 0 of the object list is its length: device + port + point
        result = await bacpypes_mcp.read_property(
            DEVICE_ADDRESS, f"device,{DEVICE_INSTANCE}", "object-list[0]"
        )
        assert result["property-array-index"] == 0
        assert result["value"] == 3

    async def test_read_property_unknown_object(self, apps) -> None:
        result = await bacpypes_mcp.read_property(
            DEVICE_ADDRESS, "analog-value,99", "present-value"
        )
        assert "value" not in result
        assert result["object-identifier"] == "analog-value,99"
        assert result["error-class"] == "object"
        assert result["error-code"] == "unknown-object"
        assert_kebab_case_keys(result)

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
            (r["object-identifier"], r["property-identifier"]): r["value"]
            for r in result
        }
        assert values == {
            ("analog-value,1", "present-value"): 12.5,
            ("analog-value,1", "units"): "no-units",
            (f"device,{DEVICE_INSTANCE}", "object-name"): "Farragut",
        }
        assert_kebab_case_keys(result)

    async def test_read_property_multiple_property_error(self, apps) -> None:
        # a per-property error comes back inline, not as a failed request
        result = await bacpypes_mcp.read_property_multiple(
            DEVICE_ADDRESS, ["analog-value,1", "present-value", "event-state"]
        )
        by_property = {r["property-identifier"]: r for r in result}
        assert by_property["present-value"]["value"] == 12.5
        assert by_property["event-state"]["error-class"] == "property"
        assert by_property["event-state"]["error-code"] == "unknown-property"
        assert_kebab_case_keys(result)


class TestDiscovery:
    async def test_who_is(self, apps) -> None:
        result = await bacpypes_mcp.who_is(low_limit=DEVICE_INSTANCE)
        assert len(result) == 1
        assert result[0]["i-am-device-identifier"] == f"device,{DEVICE_INSTANCE}"
        assert result[0]["pdu-source"] == str(Address(DEVICE_ADDRESS))
        assert_kebab_case_keys(result)

    async def test_who_has_by_name(self, apps) -> None:
        result = await bacpypes_mcp.who_has(object_name="Some point")
        assert len(result) == 1
        assert result[0]["device-identifier"] == f"device,{DEVICE_INSTANCE}"
        assert result[0]["object-identifier"] == "analog-value,1"
        assert result[0]["pdu-source"] == str(Address(DEVICE_ADDRESS))
        assert_kebab_case_keys(result)

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
