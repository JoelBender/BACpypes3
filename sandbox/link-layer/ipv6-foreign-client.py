"""
Simple console example that is a foreign device client.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.pdu import (
    Address,
    LocalStation,
    LocalBroadcast,
    IPv6Address,
    VirtualAddress,
    PDU,
)
from bacpypes3.comm import Client, bind

from bacpypes3.ipv6.service import BIPForeign, BVLLServiceElement
from bacpypes3.ipv6.bvll import BVLLCodec
from bacpypes3.ipv6 import IPv6DatagramServer


# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
foreign = None


@bacpypes_debugging
class SampleCmd(Cmd, Client[PDU]):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_send(self, address: Address, data: str) -> None:
        """
        usage: send address:Address data:str
        """
        if _debug:
            SampleCmd._debug("do_send %r %r", address, data)

        if isinstance(address, LocalBroadcast):
            pass
        elif isinstance(address, LocalStation):
            if len(address.addrAddr) != 3:
                await self.response("invalid address: " + str(address))
                return
            address = VirtualAddress(address.addrAddr)
        else:
            await self.response("invalid address: " + str(address))
            return

        pdu = PDU(data.encode(), destination=address)
        if _debug:
            SampleCmd._debug("    - pdu: %r", pdu)

        await self.request(pdu)

    def do_register(self, address: IPv6Address, ttl: int) -> None:
        """
        usage: register address:IPv6Address ttl:int
        """
        if _debug:
            SampleCmd._debug("do_register %r %r", address, ttl)

        foreign.register(address, ttl)

    def do_unregister(self) -> None:
        """
        usage: unregister
        """
        if _debug:
            SampleCmd._debug("do_unregister")

        foreign.unregister()

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            SampleCmd._debug("confirmation %r", pdu)

        await self.response(pdu.pduData.decode())

    def do_info(self) -> None:
        global normal
        foreign.debug_contents()


def main() -> None:
    global foreign
    try:
        loop = console = cmd = foreign = codec = server = None
        parser = ArgumentParser()
        parser.add_argument(
            "local_address",
            type=str,
            help="local address",
        )
        parser.add_argument(
            "virtual_address",
            type=str,
            help="virtual address",
        )
        parser.add_argument(
            "bbmd",
            type=str,
            help="BBMD address",
        )
        parser.add_argument(
            "ttl",
            type=int,
            help="time-to-live",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # get the event loop
        loop = asyncio.get_event_loop()

        # evaluate the addresses
        local_address = IPv6Address(args.local_address)
        if _debug:
            _log.debug("local_address: %r", local_address)
        virtual_address = VirtualAddress(args.virtual_address)
        if _debug:
            _log.debug("virtual_address: %r", virtual_address)
        bbmd_address = IPv6Address(args.bbmd)
        if _debug:
            _log.debug("bbmd_address: %r", bbmd_address)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        foreign = BIPForeign(virtual_address=virtual_address)
        codec = BVLLCodec()
        server = IPv6DatagramServer(loop, local_address)

        bind(console, cmd, foreign, codec, server)

        bvll_service_element = BVLLServiceElement()
        bind(bvll_service_element, foreign)

        # now start the registration process
        foreign.register(bbmd_address, args.ttl)

        # run until the console is done, canceled or EOF
        loop.run_until_complete(console.fini.wait())

        # cancel the registration
        foreign.unregister()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if server:
            server.close()
        if loop:
            loop.close()
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    main()
