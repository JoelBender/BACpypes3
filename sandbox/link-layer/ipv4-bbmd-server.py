"""
Simple IPv4 BBMD server that does _not_ have a network layer or application
layer.
"""

from __future__ import annotations

import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.pdu import IPv4Address, PDU
from bacpypes3.comm import Client, bind

from bacpypes3.ipv4.service import UDPMultiplexer, BIPBBMD
from bacpypes3.ipv4.bvll import BVLLCodec
from bacpypes3.ipv4 import IPv4DatagramServer


# some debugging
_debug = 0
_log = ModuleLogger(globals())


def main() -> None:
    try:
        loop = server = None
        parser = ArgumentParser()
        parser.add_argument(
            "address",
            type=str,
            help="listening address",
        )
        parser.add_argument(
            "peers",
            type=str,
            nargs="*",
            help="peer addresses",
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
        bbmd = BIPBBMD(address)
        for peer in args.peers:
            peer_address = IPv4Address(peer)
            bbmd.add_peer(peer_address)

        codec = BVLLCodec()
        multiplexer = UDPMultiplexer()
        server = IPv4DatagramServer(loop, address)

        bind(bbmd, codec, multiplexer.annexJ)
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
