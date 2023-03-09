"""
Virtual Local Area Network
"""

from __future__ import annotations

import asyncio
import ipaddress
import random
from copy import deepcopy

from typing import Any, List, Optional, Callable, TypeVar, Generic

from ..errors import ConfigurationError
from ..debugging import ModuleLogger, bacpypes_debugging

from ..pdu import IPv4Address, PDU
from ..comm import Client, Server, bind

AddrType = TypeVar("AddrType")

# some debugging
_debug = 0
_log = ModuleLogger(globals())

#
#   Network
#


@bacpypes_debugging
class Network(Generic[AddrType]):
    _debug: Callable[..., None]

    name: str
    nodes: List[Node[AddrType]]
    broadcast_address: Optional[AddrType]
    drop_percent: float
    traffic_log: Optional[Callable[[str, Any], None]]

    def __init__(
        self,
        name: str = "",
        broadcast_address: Optional[AddrType] = None,
        drop_percent: float = 0.0,
    ) -> None:
        if _debug:
            Network._debug(
                "__init__ name=%r broadcast_address=%r drop_percent=%r",
                name,
                broadcast_address,
                drop_percent,
            )

        self.name = name
        self.nodes = []

        self.broadcast_address = broadcast_address
        self.drop_percent = drop_percent

        # point to a TrafficLog instance
        self.traffic_log = None

    def add_node(self, node: Node[AddrType]) -> None:
        """Add a node to this network, let the node know which network it's on."""
        if _debug:
            Network._debug("add_node %r", node)

        self.nodes.append(node)
        node.lan = self

        # update the node name
        if not node.name:
            node.name = "%s:%s" % (self.name, node.address)

    def remove_node(self, node: "Node[AddrType]") -> None:
        """Remove a node from this network."""
        if _debug:
            Network._debug("remove_node %r", node)

        self.nodes.remove(node)
        node.lan = None

    async def process_pdu(self, pdu: PDU) -> None:
        """Process a PDU by sending a copy to each node as dictated by the
        addressing and if a node is promiscuous.
        """
        if _debug:
            Network._debug(
                "process_pdu(%s) %r -> %r: %r",
                self.name,
                pdu.pduSource,
                pdu.pduDestination,
                pdu,
            )

        # if there is a traffic log, call it with the network name and pdu
        if self.traffic_log:
            self.traffic_log(self.name, pdu)

        # randomly drop a packet
        if self.drop_percent != 0.0:
            if (random.random() * 100.0) < self.drop_percent:
                if _debug:
                    Network._debug("    - packet dropped")
                return

        if pdu.pduDestination == self.broadcast_address:
            if _debug:
                Network._debug("    - broadcast")
            for node in self.nodes:
                if pdu.pduSource != node.address:
                    if _debug:
                        Network._debug("    - match: %r", node)
                    await node.response(deepcopy(pdu))
        else:
            if _debug:
                Network._debug("    - unicast")
            for node in self.nodes:
                if node.promiscuous or (pdu.pduDestination == node.address):
                    if _debug:
                        Network._debug("    - match: %r", node)
                    await node.response(deepcopy(pdu))

    def __len__(self) -> int:
        """Simple way to determine the number of nodes in the network."""
        return len(self.nodes)


#
#   Node
#


@bacpypes_debugging
class Node(Generic[AddrType], Server[PDU]):
    _debug: Callable[..., None]

    address: AddrType
    lan: Optional[Network[AddrType]]
    name: str
    promiscuous: bool
    spoofing: bool

    def __init__(
        self,
        addr: AddrType,
        lan: Optional[Network[AddrType]] = None,
        name: str = "",
        promiscuous: bool = False,
        spoofing: bool = False,
        sid: Optional[str] = None,
    ) -> None:
        if _debug:
            Node._debug(
                "__init__ %r lan=%r name=%r, promiscuous=%r spoofing=%r sid=%r",
                addr,
                lan,
                name,
                promiscuous,
                spoofing,
                sid,
            )
        Server.__init__(self, sid)

        self.address = addr
        self.lan = None
        self.name = name

        # bind to a lan if it was provided
        if lan is not None:
            self.bind(lan)

        # might receive all packets and might spoof
        self.promiscuous = promiscuous
        self.spoofing = spoofing

    def bind(self, lan: Network[AddrType]) -> None:
        """Bind to a LAN."""
        if _debug:
            Node._debug("bind %r", lan)

        lan.add_node(self)

    async def indication(self, pdu: PDU) -> None:
        """Send a message."""
        if _debug:
            Node._debug("indication(%s) %r", self.name, pdu)

        # make sure we're connected
        if not self.lan:
            raise ConfigurationError("unbound node")

        # if the pduSource is unset, fill in our address, otherwise
        # leave it alone to allow for simulated spoofing
        if pdu.pduSource is None:
            pdu.pduSource = self.address
        elif (not self.spoofing) and (pdu.pduSource != self.address):
            # if _debug:
            #     Node._debug("    - spoofing address conflict")
            # return
            raise RuntimeError("spoofing address conflict")

        # make sure it gets delivered eventually
        asyncio.ensure_future(self.lan.process_pdu(pdu))

    def __repr__(self) -> str:
        return "<%s(%s) at %s>" % (
            self.__class__.__name__,
            self.name,
            hex(id(self)),
        )


#
#   IPv4Network
#


@bacpypes_debugging
class IPv4Network(Network[IPv4Address]):

    """
    IPNetwork instances are Network objects where the addresses on the
    network are instances of an IPv4Address.
    """

    _debug: Callable[..., None]
    network: ipaddress.IPv4Network

    def __init__(self, network: ipaddress.IPv4Network, name: str = "") -> None:
        if _debug:
            IPv4Network._debug("__init__ %r name=%r", network, name)
        Network.__init__(
            self, name=name, broadcast_address=IPv4Address(network.broadcast_address)
        )

        # save the network reference
        self.network = network

    def add_node(self, node: Node[IPv4Address]) -> None:
        if _debug:
            IPv4Network._debug("add_node %r", node)

        # make sure the node address is a member of the network
        if node.address not in self.network:
            raise ValueError("node not compatiable with network")

        # continue along
        Network.add_node(self, node)

    def __getitem__(self, addr: int) -> IPv4Address:
        return IPv4Address(self.network[addr])


#
#   IPv4Node
#


@bacpypes_debugging
class IPv4Node(Node[IPv4Address]):

    """
    An IPNode is a Node where the address is an Address that has an address
    tuple and a broadcast tuple that would be used for socket communications.
    """

    _debug: Callable[..., None]

    def __init__(
        self,
        addr: IPv4Address,
        lan: Optional[IPv4Network] = None,
        promiscuous: bool = False,
        spoofing: bool = False,
        sid: Optional[str] = None,
    ) -> None:
        if _debug:
            IPv4Node._debug("__init__ %r lan=%r", addr, lan)

        # make sure it's the correct kind of address
        if not isinstance(addr, IPv4Address):
            raise ValueError("malformed address")

        # continue initializing
        Node.__init__(
            self,
            addr,
            lan=lan,
            promiscuous=promiscuous,
            spoofing=spoofing,
            sid=sid,
        )


#
#   IPv4RouterNode
#


@bacpypes_debugging
class IPv4RouterNode(Client[PDU]):
    _debug: Callable[..., None]
    node: IPv4Node
    router: "IPv4Router"
    lan: IPv4Network

    def __init__(
        self, router: "IPv4Router", addr: IPv4Address, lan: IPv4Network
    ) -> None:
        if _debug:
            IPv4RouterNode._debug("__init__ %r %r lan=%r", router, addr, lan)

        # save the references to the router for packets and the lan for debugging
        self.router = router
        self.lan = lan

        # make ourselves an IPNode and bind to it
        self.node = IPv4Node(addr, lan=lan, promiscuous=True, spoofing=True)
        bind(self, self.node)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            IPv4RouterNode._debug("confirmation %r", pdu)

        await self.router.process_pdu(self, pdu)

    async def process_pdu(self, pdu: PDU) -> None:
        if _debug:
            IPv4RouterNode._debug("process_pdu %r", pdu)

        # pass it downstream
        await self.request(pdu)

    def __repr__(self) -> str:
        return "<%s at %s>" % (self.__class__.__name__, self.node.address)


#
#   IPv4Router
#


@bacpypes_debugging
class IPv4Router:
    _debug: Callable[..., None]
    nodes: List[IPv4RouterNode]

    def __init__(self) -> None:
        if _debug:
            IPv4Router._debug("__init__")

        # connected network nodes
        self.nodes = []

    def add_network(self, addr: IPv4Address, lan: IPv4Network) -> None:
        if _debug:
            IPv4Router._debug("add_network %r %r", addr, lan)

        node = IPv4RouterNode(self, addr, lan)
        if _debug:
            IPv4Router._debug("    - node: %r", node)

        self.nodes.append(node)

    async def process_pdu(self, node: IPv4RouterNode, pdu: PDU) -> None:
        if _debug:
            IPv4Router._debug("process_pdu %r %r", node, pdu)

        # loop through the other nodes
        for inode in self.nodes:
            if inode is not node:
                if _debug:
                    IPv4Router._debug("    - inode: %r", inode)
                if pdu.pduDestination in inode.lan.network:
                    if _debug:
                        IPv4Router._debug("    - processing: %r", inode)
                    await inode.process_pdu(pdu)
