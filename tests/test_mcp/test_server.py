"""
Test the bacpypes3.mcp server against the MCP Python SDK (``mcp>=2``).

The whole module is skipped when the optional ``mcp`` extra is not
installed (it requires Python 3.10+).
"""

import pytest

pytest.importorskip("mcp.server.mcpserver", reason="requires the mcp>=2 SDK")

from mcp.client import Client
from mcp.server.mcpserver import MCPServer

from bacpypes3 import mcp as bacpypes_mcp

from .conftest import DEVICE_ADDRESS, DEVICE_INSTANCE

TOOL_NAMES = {fn.__name__ for fn in bacpypes_mcp.TOOLS}


class TestBuildServer:
    async def test_registers_every_tool(self) -> None:
        server = bacpypes_mcp.build_server()
        assert isinstance(server, MCPServer)

        tools = await server.list_tools()
        assert {tool.name for tool in tools} == TOOL_NAMES
        assert len(tools) == 13

        # parameters and docstrings come through as the tool schema
        by_name = {tool.name: tool for tool in tools}
        read_property = by_name["read_property"]
        assert set(read_property.input_schema["required"]) == {
            "address",
            "object_identifier",
            "property_identifier",
        }
        assert "ReadProperty" in read_property.description

    async def test_register_tools_on_existing_server(self) -> None:
        server = MCPServer("host-app")
        assert bacpypes_mcp.register_tools(server) is server
        tools = await server.list_tools()
        assert {tool.name for tool in tools} == TOOL_NAMES

    def test_server_kwargs_are_forwarded(self) -> None:
        server = bacpypes_mcp.build_server(name="custom", version="1.2.3")
        assert server.name == "custom"

    def test_transport_kwargs_rejected_by_constructor(self) -> None:
        # mcp>=2 moved host/port to run_streamable_http_async(); the docs
        # tell callers to pass them to serve_http() instead
        with pytest.raises(TypeError):
            bacpypes_mcp.build_server(host="127.0.0.1")


class TestClientSession:
    """Drive the tools end-to-end through an in-process MCP client session."""

    async def test_session(self, apps) -> None:
        async with Client(bacpypes_mcp.build_server()) as client:
            assert client.server_info.name == "bacpypes3"

            listed = await client.list_tools()
            assert {tool.name for tool in listed.tools} == TOOL_NAMES

            result = await client.call_tool("get_config", {})
            assert not result.is_error
            config = result.structured_content["result"]
            assert config["application"][0]["object-identifier"] == "device,998"

            result = await client.call_tool(
                "read_property",
                {
                    "address": DEVICE_ADDRESS,
                    "object_identifier": "analog-value,1",
                    "property_identifier": "present-value",
                },
            )
            assert not result.is_error
            assert result.structured_content["result"]["value"] == 12.5

            result = await client.call_tool(
                "write_property",
                {
                    "address": DEVICE_ADDRESS,
                    "object_identifier": "analog-value,1",
                    "property_identifier": "present-value",
                    "value": 7.5,
                },
            )
            assert not result.is_error
            assert result.structured_content["result"] == {"ok": True}

            result = await client.call_tool(
                "read_property_multiple",
                {
                    "address": DEVICE_ADDRESS,
                    "args": ["analog-value,1", "present-value", "units"],
                },
            )
            assert not result.is_error
            values = [r["value"] for r in result.structured_content["result"]]
            assert values == [7.5, "no-units"]

            result = await client.call_tool("who_is", {"low_limit": DEVICE_INSTANCE})
            assert not result.is_error
            (i_am,) = result.structured_content["result"]
            assert i_am["i-am-device-identifier"] == f"device,{DEVICE_INSTANCE}"

    async def test_tool_error_without_application(self, no_application) -> None:
        async with Client(bacpypes_mcp.build_server()) as client:
            result = await client.call_tool("get_config", {})
            assert result.is_error

    async def test_invalid_arguments(self, apps) -> None:
        async with Client(bacpypes_mcp.build_server()) as client:
            # missing the required property_identifier
            result = await client.call_tool(
                "read_property",
                {"address": DEVICE_ADDRESS, "object_identifier": "analog-value,1"},
            )
            assert result.is_error
