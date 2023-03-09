"""
Simple console example that echos PDU messages, upper cased, and broadcasts
the response.
"""

import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.pdu import LocalBroadcast, IPv4Address, PDU
from bacpypes3.comm import Client, bind

from bacpypes3.ipv4.service import UDPMultiplexer, BIPNormal
from bacpypes3.ipv4.bvll import BVLLCodec
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

        ack = PDU(pdu.pduData.upper(), destination=LocalBroadcast())
        if _debug:
            Echo._debug("    - ack: %r", ack)

        await self.request(ack)


def main() -> None:
    try:
        loop = echo = server = None
        parser = ArgumentParser()
        parser.add_argument(
            "address",
            type=str,
            help="listening address",
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
        echo = Echo()
        simple = BIPNormal()
        codec = BVLLCodec()
        multiplexer = UDPMultiplexer()
        server = IPv4DatagramServer(loop, address)

        bind(echo, simple, codec, multiplexer.annexJ)
        bind(multiplexer, server)

        # run a really long time
        loop.run_forever()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if server:
            server.close()
        if loop:
            loop.close()


if __name__ == "__main__":
    main()
