#!/usr/bin/python

"""
Simple IPv6 BBMD server that does _not_ have a network layer or application
layer.
"""

import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.pdu import IPv6Address, VirtualAddress, PDU
from bacpypes3.comm import Client, bind

from bacpypes3.ipv6.service import BIPBBMD, BVLLServiceElement
from bacpypes3.ipv6.bvll import BVLLCodec
from bacpypes3.ipv6 import IPv6DatagramServer


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
            "virtual_address",
            type=str,
            help="virtual address",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # get the event loop
        loop = asyncio.get_event_loop()

        # evaluate the addresses
        address = IPv6Address(args.address)
        if _debug:
            _log.debug("address: %r", address)
        virtual_address = VirtualAddress(args.virtual_address)
        if _debug:
            _log.debug("virtual_address: %r", virtual_address)

        # build a very small stack
        bbmd = BIPBBMD(bbmd_address=address, virtual_address=virtual_address)
        codec = BVLLCodec()
        server = IPv6DatagramServer(loop, address)

        bind(bbmd, codec, server)

        bvll_service_element = BVLLServiceElement()
        bind(bvll_service_element, normal)

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
