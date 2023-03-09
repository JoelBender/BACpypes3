"""
Simple console example that sends messages.
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

from bacpypes3.ipv4.service import UDPMultiplexer, BIPNormal
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

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            SampleCmd._debug("confirmation %r", pdu)

        await self.response(pdu.pduData.decode())


def main() -> None:
    try:
        loop = console = cmd = server = None
        parser = ArgumentParser()
        parser.add_argument(
            "address",
            type=str,
            help="address",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # get the event loop
        loop = asyncio.get_event_loop()

        # evaluate the address
        address = IPv4Address(args.address)
        if _debug:
            _log.debug("address: %r", address)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        simple = BIPNormal()
        codec = BVLLCodec()
        multiplexer = UDPMultiplexer()
        server = IPv4DatagramServer(loop, address)

        bind(console, cmd, simple, codec, multiplexer.annexJ)  # type: ignore[arg-type]
        bind(multiplexer, server)  # type: ignore[arg-type]

        # run until the console is done, canceled or EOF
        loop.run_until_complete(console.fini.wait())

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
