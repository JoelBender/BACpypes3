#!/usr/bin/python

"""
Simple console example that sends IPv6 UDP messages.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.comm import Client, bind
from bacpypes3.pdu import Address, LocalBroadcast, IPv6Address, PDU
from bacpypes3.ipv6 import IPv6DatagramServer

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
        usage: send address:IPv6Address data:str
        """
        if _debug:
            SampleCmd._debug("do_send %r %r", address, data)

        if not isinstance(address, (IPv6Address, LocalBroadcast)):
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

        await self.response(str(pdu.pduData.decode()))


async def main() -> None:
    try:
        console = server = None
        parser = ArgumentParser()
        parser.add_argument(
            "address",
            type=str,
            nargs="?",
            default="[::]",
            help="listening address (default [::])",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # evaluate the address
        address = IPv6Address(args.address)
        if _debug:
            _log.debug("address: %r", address)

        # build a very small stack
        server = IPv6DatagramServer(address)
        cmd = SampleCmd()
        console = Console()
        bind(console, cmd, server)  # type: ignore[misc]

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if server:
            server.close()
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
