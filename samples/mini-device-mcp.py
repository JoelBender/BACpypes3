#!/usr/bin/env python3
"""
Mini BACnet Device + Embedded MCP Server
========================================

A minimal BACnet server (the same four points as ``mini-device-revisited.py``)
that ALSO exposes an MCP (Model Context Protocol) server on HTTP so an LLM
agent can drive it from outside the process.

This is the reference pattern for embedding ``bacpypes3.mcp`` in a
long-running application that owns its own :class:`Application`. Two
things make it work:

1. Inject the running app: ``mcp.set_application(self.app)``.
2. Start MCP as a concurrent asyncio task on a transport that does not
   touch stdio: ``mcp.serve_http(...)``. (Do NOT use ``serve_stdio`` —
   it would fight this process's own stdout.)

The MCP client connects to ``http://127.0.0.1:8765/mcp`` and can call
tools like ``who_is``, ``read_property``, ``write_property``, and
``get_config``. Because the injected app is this device, ``get_config``
returns THIS server's identity and object list; ``read_property`` /
``write_property`` use this server's network stack to talk to remote
devices, and remote clients can independently poll and command the four
local objects hosted here.

Usage
-----
Install the ``mcp`` extra first::

    pip install -e ".[mcp]"

Then::

    python samples/mini-device-mcp.py --name Demo --instance 3456
"""

import asyncio
import logging
import sys

from bacpypes3.app import Application
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject
from bacpypes3.local.cmd import Commandable

from bacpypes3 import mcp

_debug = 0
_log = ModuleLogger(globals())

INTERVAL = 5.0


@bacpypes_debugging
class CommandableAnalogValueObject(Commandable, AnalogValueObject):
    """Commandable Analog Value Object"""


@bacpypes_debugging
class CommandableBinaryValueObject(Commandable, BinaryValueObject):
    """Commandable Binary Value Object"""


@bacpypes_debugging
class SampleApplication:
    def __init__(self, args):
        # Build the BACnet application (DeviceObject from args).
        self.app = Application.from_args(args)

        self.read_only_av = AnalogValueObject(
            objectIdentifier=("analogValue", 1),
            objectName="read-only-av",
            presentValue=4.0,
            statusFlags=[0, 0, 0, 0],
            covIncrement=1.0,
            units="degreesFahrenheit",
            description="Simulated Read-Only Analog Value",
        )
        self.read_only_bv = BinaryValueObject(
            objectIdentifier=("binaryValue", 1),
            objectName="read-only-bv",
            presentValue="active",
            statusFlags=[0, 0, 0, 0],
            description="Simulated Read-Only Binary Value",
        )
        self.commandable_av = CommandableAnalogValueObject(
            objectIdentifier=("analogValue", 2),
            objectName="commandable-av",
            presentValue=0.0,
            statusFlags=[0, 0, 0, 0],
            covIncrement=1.0,
            units="degreesFahrenheit",
            description="Commandable Analog Value (Simulated)",
        )
        self.commandable_bv = CommandableBinaryValueObject(
            objectIdentifier=("binaryValue", 2),
            objectName="commandable-bv",
            presentValue="inactive",
            statusFlags=[0, 0, 0, 0],
            description="Commandable Binary Value (Simulated)",
        )

        for obj in (
            self.read_only_av,
            self.read_only_bv,
            self.commandable_av,
            self.commandable_bv,
        ):
            self.app.add_object(obj)

        # Simulate activity on the read-only points.
        asyncio.create_task(self.update_values())

        # --- Embed the MCP server -------------------------------------
        # 1. Point the mcp tool functions at THIS application, so that
        #    e.g. get_config reports this device's identity and reads
        #    use this app's network stack.
        mcp.set_application(self.app)

        # 2. Start the MCP HTTP transport as a concurrent task so it
        #    coexists with the BACnet server and any other work.
        #    Loopback-only by default; put it behind an auth proxy if
        #    you need to expose it beyond the host.
        self.mcp_task = asyncio.create_task(
            mcp.serve_http(host="127.0.0.1", port=8765)
        )
        _log.info("MCP server listening on http://127.0.0.1:8765/mcp")

    async def update_values(self) -> None:
        test_values = [
            ("active", 1.0),
            ("inactive", 2.0),
            ("active", 3.0),
            ("inactive", 4.0),
        ]
        while True:
            await asyncio.sleep(INTERVAL)
            next_value = test_values.pop(0)
            test_values.append(next_value)
            self.read_only_av.presentValue = next_value[1]
            self.read_only_bv.presentValue = next_value[0]


async def main() -> None:
    parser = SimpleArgumentParser()
    parser.add_argument(
        "--mcp-debug",
        action="store_true",
        help=(
            "Turn on DEBUG-level logging for the embedded MCP / uvicorn "
            "transport. Surfaces per-request access lines, session-manager "
            "routing, and lifecycle events. Note: the reason for a "
            "Streamable-HTTP 400 is written into the response body, not "
            "logged, so read it on the CLIENT side (curl prints it; "
            "ollmcp needs -v / HTTPX_LOG_LEVEL=trace)."
        ),
    )
    args = parser.parse_args()

    # When --mcp-debug is passed, wire up logging BEFORE serve_http runs.
    # MCPServer.run_streamable_http_async() calls configure_logging(),
    # which in turn calls logging.basicConfig(...); basicConfig is a
    # no-op once the root logger already has handlers attached, so as
    # long as we install ours first they survive and MCP does not clobber
    # them. If we deferred this to after serve_http, MCP would win and
    # only INFO would come through.
    if args.mcp_debug:
        logging.basicConfig(level=logging.DEBUG)
        for name in (
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
            "mcp",
            "mcp.server",
            "mcp.server.streamable_http",
        ):
            logging.getLogger(name).setLevel(logging.DEBUG)

    SampleApplication(args)

    # Run forever.
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _log.info("Keyboard interrupt received, shutting down.")
        sys.exit(0)
