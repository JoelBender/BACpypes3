#!/usr/bin/python

"""
Simple console example that sends Initialize Routing Table messages.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.comm import Client, bind
from bacpypes3.pdu import Address, LocalBroadcast, IPv4Address, PDU
from bacpypes3.ipv4.link import NormalLinkLayer

from bacpypes3.npdu import NPCI, NPDU, npdu_types, InitializeRoutingTable, InitializeRoutingTableAck

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class SampleCmd(Cmd, Client[PDU]):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_irt(self, address: Address) -> None:
        """
        usage: irt address:Address
        """
        if _debug:
            SampleCmd._debug("do_irt %r", address)

        npdu = InitializeRoutingTable([])
        if _debug:
            SampleCmd._debug("    - npdu: %r", npdu)

        # the hop count always starts out big
        npdu.npduHopCount = 255

        # if this is route aware, use it for the destination
        if address.addrRoute:
            if address.addrType in (
                Address.remoteStationAddr,
                Address.remoteBroadcastAddr,
                Address.globalBroadcastAddr,
            ):
                if _debug:
                    SampleCmd._debug(
                        "    - continue DADR: %r", npdu.pduDestination
                    )
                npdu.npduDADR = address
            npdu.pduDestination = address.addrRoute

            await self.encode_and_request(npdu)
            return

        # local stations given to local adapter
        if address.addrType in (Address.localStationAddr, Address.localBroadcastAddr):
            npdu.pduDestination = address
            await self.encode_and_request(npdu)
            return

        # global broadcast
        if address.addrType == Address.globalBroadcastAddr:
            # set the destination
            npdu.pduDestination = LocalBroadcast()
            npdu.npduDADR = address
            await self.encode_and_request(npdu)
            return

        # remote broadcast
        if (npdu.pduDestination.addrType != Address.remoteBroadcastAddr) and (
            npdu.pduDestination.addrType != Address.remoteStationAddr
        ):
            raise RuntimeError(
                "use route-aware for remote broadcast")

    async def encode_and_request(self, npdu):
        pdu = npdu.encode()
        if _debug:
            SampleCmd._debug("    - pdu: %r", pdu)
        
        await self.request(pdu)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            SampleCmd._debug("confirmation %r", pdu)

        # decode as an NPDU
        npdu = NPDU.decode(pdu)

        # if this is a network layer message, find the subclass and let it
        # decode the message
        if npdu.npduNetMessage is None:
            return

        try:
            npdu_class = npdu_types[npdu.npduNetMessage]
        except KeyError:
            raise RuntimeError(f"unrecognized NPDU type: {npdu.npduNetMessage}")
        if _debug:
            SampleCmd._debug("    - npdu_class: %r", npdu_class)

        # ask the class to decode the rest of the PDU
        xpdu = npdu_class.decode(npdu)
        NPCI.update(xpdu, npdu)
        if _debug:
            SampleCmd._debug("    - xpdu: %r", xpdu)

        if not isinstance(xpdu, InitializeRoutingTableAck):
            return

        if xpdu.npduSADR:
            print(f"{xpdu.npduSADR}@{xpdu.pduSource}")
        else:
            print(xpdu.pduSource)

        report = []
        for routing_table_entry in xpdu.irtaTable:
            report.append(
                f"    {routing_table_entry.rtDNET:-5} {routing_table_entry.rtPortID}"
            )

        await self.response("\n".join(report))

async def main() -> None:
    try:
        console = cmd = server = None
        parser = ArgumentParser()
        parser.add_argument(
            "local_address",
            type=str,
            help="local address (e.g., 'host:47808')",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        settings.route_aware = True
        if _debug:
            _log.debug("settings: %r", settings)

        # evaluate the address
        local_address = IPv4Address(args.local_address)
        if _debug:
            _log.debug("local_address: %r", local_address)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        server = NormalLinkLayer(local_address)
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
