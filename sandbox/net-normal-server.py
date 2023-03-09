"""
Simple console example that echos PDU messages, upper cased.
"""

import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.pdu import IPv4Address, PDU
from bacpypes3.comm import Client, bind

from bacpypes3.netservice import NetworkServiceAccessPoint, NetworkServiceElement

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

        ack = PDU(pdu.pduData.upper(), destination=pdu.pduSource)
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
        ipv4_address = IPv4Address(args.address)
        if _debug:
            _log.debug("ipv4_address: %r", ipv4_address)

        # application layer
        echo = Echo()

        # network layer
        npdu_nsap = NetworkServiceAccessPoint()
        npdu_nse = NetworkServiceElement()
        bind(npdu_nse, npdu_nsap)  # type: ignore[arg-type]

        # bind the upper layers together
        bind(echo, npdu_nsap)

        # create a link layer
        bvll_normal = BIPNormal()
        bvll_codec = BVLLCodec()
        multiplexer = UDPMultiplexer()
        server = IPv4DatagramServer(loop, ipv4_address)
        bind(multiplexer, server)  # type: ignore[arg-type]
        bind(bvll_normal, bvll_codec, multiplexer.annexJ)  # type: ignore[arg-type]

        # connect the network layer to the link layer
        npdu_nsap.bind(bvll_normal)

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
