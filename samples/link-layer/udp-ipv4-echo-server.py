#!/usr/bin/python

"""
Simple console example that echos IPv4 UDP messages, upper cased.
"""

import asyncio

from typing import Callable

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.comm import Client, bind
from bacpypes3.pdu import IPv4Address, PDU
from bacpypes3.ipv4 import IPv4DatagramServer


# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class Echo(Client[PDU]):
    """
    Echo
    """

    _debug: Callable[..., None]

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            Echo._debug("confirmation %r", pdu)

        ack = PDU(pdu.pduData.upper(), destination=pdu.pduSource)
        if _debug:
            Echo._debug("    - ack: %r", ack)

        await self.request(ack)


async def main() -> None:
    try:
        echo = server = None
        parser = ArgumentParser()
        parser.add_argument(
            "local_address",
            type=str,
            # nargs="?",
            help="local address",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # evaluate the address
        local_address = IPv4Address(args.local_address)
        if _debug:
            _log.debug("local_address: %r", local_address)

        # build a very small stack
        echo = Echo()
        server = IPv4DatagramServer(local_address)
        bind(echo, server)

        # run a really long time
        await asyncio.Future()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if server:
            server.close()


if __name__ == "__main__":
    asyncio.run(main())
