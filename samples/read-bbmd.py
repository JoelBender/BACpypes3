"""
Simple example that reads the broadcast distibution table or foreign device
table from a BACnet/IPv4 device.  This builds a complete stack but only uses
the BVLL service access point for an application service element.
"""

import asyncio

from typing import Callable

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd
from bacpypes3.comm import bind, ApplicationServiceElement

from bacpypes3.pdu import IPv4Address
from bacpypes3.ipv4.bvll import (
    LPDU,
    ReadBroadcastDistributionTable,
    ReadBroadcastDistributionTableAck,
    ReadForeignDeviceTable,
    ReadForeignDeviceTableAck,
)
from bacpypes3.ipv4.service import BVLLServiceAccessPoint

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
app: Application
ase: "BVLLServiceElement"


@bacpypes_debugging
class BVLLServiceElement(ApplicationServiceElement):
    _debug: Callable[..., None]

    def __init__(self):
        self.read_bdt_future = None
        self.read_fdt_future = None

    async def confirmation(self, pdu: LPDU):
        if _debug:
            BVLLServiceElement._debug("confirmation %r", pdu)

        if isinstance(pdu, ReadBroadcastDistributionTableAck):
            self.read_bdt_future.set_result(pdu.bvlciBDT)
            self.read_bdt_future = None

        elif isinstance(pdu, ReadForeignDeviceTableAck):
            self.read_fdt_future.set_result(pdu.bvlciFDT)
            self.read_fdt_future = None

    def read_broadcast_distribution_table(self, address: IPv4Address) -> asyncio.Future:
        if _debug:
            BVLLServiceElement._debug("read_broadcast_distribution_table %r", address)

        self.read_bdt_future = asyncio.Future()
        if _debug:
            BVLLServiceElement._debug("    - read_bdt_future: %r", self.read_bdt_future)

        asyncio.ensure_future(
            self.request(ReadBroadcastDistributionTable(destination=address))
        )

        return self.read_bdt_future

    def read_foreign_device_table(self, address: IPv4Address) -> asyncio.Future:
        if _debug:
            BVLLServiceElement._debug("read_broadcast_distribution_table %r", address)

        self.read_fdt_future = asyncio.Future()
        if _debug:
            BVLLServiceElement._debug("    - read_bdt_future: %r", self.read_bdt_future)

        asyncio.ensure_future(self.request(ReadForeignDeviceTable(destination=address)))

        return self.read_fdt_future


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_rbdt(
        self,
        address: IPv4Address,
    ) -> None:
        """
        usage: rbdt address
        """
        if _debug:
            SampleCmd._debug("do_rbdt %r", address)

        result = await ase.read_broadcast_distribution_table(address)
        await self.response(str(result))

    async def do_rfdt(
        self,
        address: IPv4Address,
    ) -> None:
        """
        usage: rfdt address
        """
        if _debug:
            SampleCmd._debug("do_rfdt %r", address)

        result = await ase.read_foreign_device_table(address)
        await self.response(str(result))


async def main() -> None:
    global app, ase

    app = None
    try:
        parser = SimpleArgumentParser()
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # pick out the BVLL service access point from the local adapter
        local_adapter = app.nsap.local_adapter
        if _debug:
            _log.debug("local_adapter: %r", local_adapter)
        sap = local_adapter.clientPeer
        assert isinstance(sap, BVLLServiceAccessPoint)
        if _debug:
            _log.debug("sap: %r", sap)

        # create a service element
        ase = BVLLServiceElement()
        if _debug:
            _log.debug("ase: %r", ase)

        bind(ase, sap)

        # wait until the user is done
        await console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
