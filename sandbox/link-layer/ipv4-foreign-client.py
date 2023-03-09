#!/usr/bin/python

"""
Simple console example that sends IPv4 UDP messages.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.pdu import Address, LocalBroadcast, IPv4Address, PDU
from bacpypes3.comm import Client, bind

from bacpypes3.ipv4.service import UDPMultiplexer, BIPForeign
from bacpypes3.ipv4.bvll import BVLLCodec
from bacpypes3.ipv4 import IPv4DatagramServer


# some debugging
_debug = 0
_log = ModuleLogger(globals())


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

        if not isinstance(address, (IPv4Address, LocalBroadcast)):
            if _debug:
                SampleCmd._debug("    - invalid address: %r", address)
            await self.response("invalid address: " + str(address))
            return

        pdu = PDU(data.encode(), destination=address)
        if _debug:
            SampleCmd._debug("    - pdu: %r", pdu)

        await self.request(pdu)

    def do_register(self, address: Address, ttl: int) -> None:
        """
        usage: register address:Address ttl:int
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


def main() -> None:
    global foreign
    try:
        loop = console = cmd = foreign = codec = multiplexer = server = None
        parser = ArgumentParser()
        parser.add_argument(
            "address",
            type=str,
            help="address",
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
        local_address = IPv4Address(args.address)
        if _debug:
            _log.debug("local_address: %r", local_address)
        bbmd_address = IPv4Address(args.bbmd)
        if _debug:
            _log.debug("bbmd_address: %r", bbmd_address)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        foreign = BIPForeign()
        codec = BVLLCodec()
        multiplexer = UDPMultiplexer()
        server = IPv4DatagramServer(loop, local_address)

        bind(console, cmd, foreign, codec, multiplexer.annexJ)
        bind(multiplexer, server)

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
