"""
VLAN Console

This example creates a VLAN network with two nodes, a "console node" and an
"echo node".  The console node presents a prompt for 'send <addr> <data>'
where the <addr> is the address of the echo node or a local broadcast.  The
echo node returns the data converted to uppercase.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.pdu import Address, LocalBroadcast, PDU
from bacpypes3.comm import Client, bind
from bacpypes3.vlan import Network, Node

from bacpypes3.netservice import NetworkServiceAccessPoint, NetworkServiceElement

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class TestNetwork(Network[Address]):
    """
    Virtual networks can be built with any type of object for addressing which
    makes it simple to simulate IPv4 and IPv6 networks as well as simpler ones
    like MS/TP.
    """

    _debug: Callable[..., None]

    def __init__(self) -> None:
        if _debug:
            TestNetwork._debug("__init__")
        super().__init__(broadcast_address=LocalBroadcast())


@bacpypes_debugging
class TestNode(Node[Address]):
    _debug: Callable[..., None]

    def __init__(self, address: Address, lan: TestNetwork) -> None:
        if _debug:
            TestNode._debug("__init__ %r %r", address, lan)
        super().__init__(address, lan)

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            TestNode._debug("indication %r", pdu)

        await super().indication(pdu)

    async def response(self, pdu: PDU) -> None:
        if _debug:
            TestNode._debug("response %r", pdu)

        await super().response(pdu)


@bacpypes_debugging
class ConsoleCmd(Cmd, Client[PDU]):
    """
    Console interface, sends string data downstream to the network and prints
    the data received upstream.
    """

    _debug: Callable[..., None]

    async def do_send(self, address: Address, data: str) -> None:
        """
        usage: send address:int data:str
        """
        if _debug:
            ConsoleCmd._debug("do_send %r %r", address, data)

        pdu = PDU(data.encode(), destination=address)
        if _debug:
            ConsoleCmd._debug("    - pdu: %r", pdu)

        await self.request(pdu)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            ConsoleCmd._debug("confirmation %r", pdu)

        await self.response(pdu.pduData.decode())


@bacpypes_debugging
class ConsoleNode:
    """
    Network stack for the console.  Note that the application layer is not
    BACnet, it's just strings, but the stack contains the BACnet networking
    layer with a TestNode instance at the bottom as the link layer.
    """

    _debug: Callable[..., None]

    console: Console

    def __init__(self, address: Address, net: TestNetwork) -> None:
        if _debug:
            ConsoleNode._debug("__init__ %r %r", address, net)

        # application layer
        self.console = Console()
        self.fini = self.console.fini
        console_cmd = ConsoleCmd()

        # network layer
        npdu_nsap = NetworkServiceAccessPoint()
        npdu_nse = NetworkServiceElement()
        bind(npdu_nse, npdu_nsap)  # type: ignore[arg-type]

        # bind the upper layers together
        bind(self.console, console_cmd, npdu_nsap)

        # link layer
        node = TestNode(address, net)

        # connect the network layer to the link layer
        npdu_nsap.bind(node)


@bacpypes_debugging
class Echo(Client[PDU]):
    """
    Everything that is received coming upstream, unicast or broadcast, is
    converted to uppercase and sent unicast back to the source.
    """

    _debug: Callable[..., None]

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            Echo._debug("confirmation %r", pdu)

        ack = PDU(pdu.pduData.upper(), destination=pdu.pduSource)
        if _debug:
            Echo._debug("    - ack: %r", ack)

        await self.request(ack)


@bacpypes_debugging
class EchoNode:
    """
    Network stack for the echo service.
    """

    _debug: Callable[..., None]

    console: Console

    def __init__(self, address: Address, net: TestNetwork) -> None:
        if _debug:
            EchoNode._debug("__init__ %r %r", address, net)

        # application layer
        echo_service = Echo()

        # network layer
        npdu_nsap = NetworkServiceAccessPoint()
        npdu_nse = NetworkServiceElement()
        bind(npdu_nse, npdu_nsap)  # type: ignore[arg-type]

        # bind the upper layers together
        bind(echo_service, npdu_nsap)

        # link layer
        node = TestNode(address, net)

        # connect the network layer to the link layer
        npdu_nsap.bind(node)


async def main() -> None:
    try:
        network = console_node = None
        ArgumentParser().parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # network
        network = TestNetwork()

        # console and service
        console_node = ConsoleNode(Address(1), network)
        if _debug:
            _log.debug("console_node: %r", console_node)

        # echo node
        echo_node = EchoNode(Address(2), network)
        if _debug:
            _log.debug("echo_node: %r", echo_node)

        # run until the console is done, canceled or EOF
        await console_node.console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if console_node and console_node.console.exit_status:
            sys.exit(console_node.console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
