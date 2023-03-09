"""
VLAN Console Router

This example has a console node and an echo service node that sit on
different networks with a BACnet router between them.  There are four networks,
the first router is between networks 1, 2, and 3, the second router is between
3 and 4.
"""

import sys
import asyncio

from typing import Callable, Tuple

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

# globals
console_nsap = None
console_nse = None
router_1 = None
router_2 = None


@bacpypes_debugging
class TestNetwork(Network[Address]):
    _debug: Callable[..., None]

    def __init__(self, *, name: str) -> None:
        if _debug:
            TestNetwork._debug("__init__")
        super().__init__(name=name, broadcast_address=LocalBroadcast())

        # this special hook for VLANs helps track what is being sent
        self.traffic_log = lambda name, pdu: sys.stdout.write(f"{name}: {pdu}\n")


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
    Sample Cmd
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

    async def do_wirtn(self, dnet: int) -> None:
        """
        usage: wirtn dnet:int
        """
        if _debug:
            ConsoleCmd._debug("do_wirtn %r", dnet)
        global console_nse

        try:
            i_am_routers = await asyncio.wait_for(
                console_nse.who_is_router_to_network(adapter=None, network=dnet),
                timeout=4,
            )
            for router_adapter, router_to_network in i_am_routers:
                if _debug:
                    ConsoleCmd._debug("    - router_adapter: %r", router_adapter)
                    ConsoleCmd._debug("    - router_to_network: %r", router_to_network)

                await self.response(
                    f"{router_to_network.pduSource} {router_to_network.iartnNetworkList}"
                )

        except asyncio.TimeoutError:
            await self.response("timeout")

    async def do_iartn(self) -> None:
        """
        usage: iartn
        """
        if _debug:
            ConsoleCmd._debug("do_iartn")
        global router_nse

        await router_nse.i_am_router_to_network()

    async def do_winn(self) -> None:
        """
        usage: winn
        """
        if _debug:
            ConsoleCmd._debug("do_wirtn")
        global console_nse

        try:
            network = await asyncio.wait_for(
                console_nse.what_is_network_number(),
                timeout=4,
            )
            await self.response(f"network number is {network}")
        except asyncio.TimeoutError:
            await self.response("timeout")

    def do_debug(self) -> None:
        global console_nsap, console_nse

        print("console_nsap")
        console_nsap.debug_contents()

        print("console_nse")
        console_nse.debug_contents()

        print("router_1.nsap")
        router_1.nsap.debug_contents()

        print("router_1.nse")
        router_1.nse.debug_contents()


@bacpypes_debugging
class ConsoleNode:
    """
    Network stack for the console.
    """

    _debug: Callable[..., None]

    console: Console
    node: TestNode

    def __init__(self, address: Address, net: TestNetwork) -> None:
        if _debug:
            ConsoleNode._debug("__init__ %r %r", address, net)

        # expose the network service element
        global console_nsap, console_nse

        # application layer
        self.console = Console()
        self.fini = self.console.fini
        console_cmd = ConsoleCmd()

        # network layer
        console_nsap = NetworkServiceAccessPoint()
        console_nse = NetworkServiceElement()
        bind(console_nse, console_nsap)  # type: ignore[arg-type]

        # bind the upper layers together
        bind(self.console, console_cmd, console_nsap)

        # link layer
        self.node = TestNode(address, net)

        # connect the network layer to the link layer
        console_nsap.bind(self.node)


@bacpypes_debugging
class Echo(Client[PDU]):
    """
    Echo service
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
    node: TestNode

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
        self.node = TestNode(address, net)

        # connect the network layer to the link layer
        npdu_nsap.bind(self.node)


class Router:
    def __init__(self, *binding_list: Tuple[int, Address, TestNetwork]) -> None:
        # network layer only
        self.nsap = NetworkServiceAccessPoint()
        self.nse = NetworkServiceElement()
        bind(self.nse, self.nsap)  # type: ignore[arg-type]

        # make a node for each network
        for network_number, address, network in binding_list:
            router_node = TestNode(address, network)
            self.nsap.bind(router_node, network_number, address)


async def main() -> None:
    global router_1, router_2

    try:
        console_node = None
        ArgumentParser().parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # network 1 and console
        network_1 = TestNetwork(name="net1")
        console_node = ConsoleNode(Address(1), network_1)
        if _debug:
            _log.debug("console_node (1): %r", console_node)

        # network 2 and echo service
        network_2 = TestNetwork(name="net2")
        echo_node = EchoNode(Address(2), network_2)
        if _debug:
            _log.debug("echo_node (2): %r", echo_node)

        # network 3 and echo service
        network_3 = TestNetwork(name="net3")
        echo_node = EchoNode(Address(3), network_3)
        if _debug:
            _log.debug("echo_node (3): %r", echo_node)

        # router
        router_1 = Router(
            (1, Address(4), network_1),
            (2, Address(5), network_2),
            (3, Address(6), network_3),
        )
        if _debug:
            _log.debug("router_1: %r", router_1)

        # network 4 and echo service
        network_4 = TestNetwork(name="net4")
        echo_node = EchoNode(Address(7), network_4)
        if _debug:
            _log.debug("echo_node (7): %r", echo_node)

        # router
        router_2 = Router(
            (3, Address(8), network_3),
            (4, Address(9), network_4),
        )
        if _debug:
            _log.debug("router_2: %r", router_2)

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
