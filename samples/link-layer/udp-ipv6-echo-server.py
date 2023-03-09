#!/usr/bin/python

"""
Simple console example that echos IPv6 UDP messages, upper cased.  Given this
IP configuration:

    $ ip addr
    2: enp0s25: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ...
        link/ether 00:23:ae:95:c2:82 brd ff:ff:ff:ff:ff:ff
        inet 10.0.1.90/24 brd 10.0.1.255 scope global dynamic noprefixroute enp0s25
           valid_lft 82093sec preferred_lft 82093sec
        inet6 fe80::1b99:de63:cdd6:67a9/64 scope link noprefixroute
           valid_lft forever preferred_lft forever

Examples:

    $ python3 samples/udp-ipv6-echo-server.py [::]:47809
    $ python3 samples/udp-ipv6-echo-server.py [fe80::1b99:de63:cdd6:67a9/64]:47809%enp0s25
"""

import asyncio

from typing import Callable

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.comm import Client, bind
from bacpypes3.pdu import IPv6Address, PDU
from bacpypes3.ipv6 import IPv6DatagramServer

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
        server = None
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
        echo = Echo()
        server = IPv6DatagramServer(address)
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
