"""
Network Service
"""

from __future__ import annotations

import asyncio
import inspect
from copy import deepcopy as _deepcopy

from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    cast,
)

from .settings import settings
from .debugging import ModuleLogger, DebugContents, bacpypes_debugging
from .errors import ConfigurationError, UnknownRoute

from .comm import Client, Server, bind, ServiceAccessPoint, ApplicationServiceElement

from .pdu import (
    Address,
    LocalBroadcast,
    LocalStation,
    PCI,
    PDU,
    RemoteStation,
    GlobalBroadcast,
)
from .npdu import (
    NPCI,
    NPDU,
    npdu_types,
    IAmRouterToNetwork,
    WhoIsRouterToNetwork,
    WhatIsNetworkNumber,
    NetworkNumberIs,
    RoutingTableEntry,
    InitializeRoutingTable,
    InitializeRoutingTableAck,
)
from .basetypes import NetworkNumberQuality

if TYPE_CHECKING:
    # class is declared as generic in stubs but not at runtime
    WhatIsNetworkNumberFuture = asyncio.Future[int]
else:
    WhatIsNetworkNumberFuture = asyncio.Future

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# settings
WHO_IS_ROUTER_TO_NETWORK_TIMEOUT = 2.0
INITIALIZE_ROUTING_TABLE_TIMEOUT = 3.0

# router status values
ROUTER_AVAILABLE = 0  # normal
ROUTER_BUSY = 1  # router is busy
ROUTER_DISCONNECTED = 2  # could make a connection, but hasn't
ROUTER_UNREACHABLE = 3  # temporarily unreachable

#
#   RouterInfo
#


class RouterInfo(DebugContents):
    """
    These objects are routing information records that map router
    addresses with destination networks.
    """

    _debug_contents: Tuple[str, ...] = ("snet", "address", "dnets")

    snet: Optional[int]
    address: Address
    dnets: Dict[int, int]

    def __init__(self, snet: Optional[int], address: Address) -> None:
        self.snet = snet  # source network
        self.address = address  # address of the router
        self.dnets = {}  # {dnet: status}

    def set_status(self, dnets, status) -> None:
        """Change the status of each of the DNETS."""
        for dnet in dnets:
            self.dnets[dnet] = status


#
#   RouterInfoCache
#


@bacpypes_debugging
class RouterInfoCache(DebugContents):
    """
    This class provides an in-memory implementation of a database of RouterInfo
    objects.
    """

    _debug_contents = (
        "routers+",
        "path_info+",
    )
    _debug: Callable[..., None]

    routers: Dict[Optional[int], Dict[Address, RouterInfo]]
    path_info: Dict[Tuple[Optional[int], int], RouterInfo]

    def __init__(self):
        if _debug:
            RouterInfoCache._debug("__init__")

        self.routers = {}  # snet -> {Address: RouterInfo}
        self.path_info = {}  # (snet, dnet) -> RouterInfo

    def get_router_info(self, snet: Optional[int], dnet: int) -> Optional[RouterInfo]:
        if _debug:
            RouterInfoCache._debug("get_router_info %r %r", snet, dnet)

        # return the network and address
        router_info = self.path_info.get((snet, dnet), None)
        if _debug:
            RouterInfoCache._debug("   - router_info: %r", router_info)

        return router_info

    def update_router_info(
        self,
        snet: Optional[int],
        address: Address,
        dnets: List[int],
        status: int = ROUTER_AVAILABLE,
    ) -> None:
        if _debug:
            RouterInfoCache._debug("update_router_info %r %r %r", snet, address, dnets)

        existing_router_info = self.routers.get(snet, {}).get(address, None)

        other_routers = set()
        for dnet in dnets:
            other_router = self.path_info.get((snet, dnet), None)
            if other_router and (other_router is not existing_router_info):
                other_routers.add(other_router)

        # remove the dnets from other router(s) and paths
        if other_routers:
            for router_info in other_routers:
                for dnet in dnets:
                    if dnet in router_info.dnets:
                        del router_info.dnets[dnet]
                        del self.path_info[(snet, dnet)]
                        if _debug:
                            RouterInfoCache._debug(
                                "    - del path: %r -> %r via %r",
                                snet,
                                dnet,
                                router_info.address,
                            )
                if not router_info.dnets:
                    del self.routers[snet][router_info.address]
                    if _debug:
                        RouterInfoCache._debug(
                            "    - no dnets: %r via %r", snet, router_info.address
                        )

        # update current router info if there is one
        if not existing_router_info:
            router_info = RouterInfo(snet, address)
            if snet not in self.routers:
                self.routers[snet] = {address: router_info}
            else:
                self.routers[snet][address] = router_info

            for dnet in dnets:
                self.path_info[(snet, dnet)] = router_info
                if _debug:
                    RouterInfoCache._debug(
                        "    - add path: %r -> %r via %r",
                        snet,
                        dnet,
                        router_info.address,
                    )
                router_info.dnets[dnet] = status
        else:
            for dnet in dnets:
                if dnet not in existing_router_info.dnets:
                    self.path_info[(snet, dnet)] = existing_router_info
                    if _debug:
                        RouterInfoCache._debug("    - add path: %r -> %r", snet, dnet)
                existing_router_info.dnets[dnet] = status

    def update_router_status(self, snet: int, address: Address, status: int) -> None:
        if _debug:
            RouterInfoCache._debug(
                "update_router_status %r %r %r", snet, address, status
            )

        existing_router_info = self.routers.get(snet, {}).get(address, None)
        if not existing_router_info:
            if _debug:
                RouterInfoCache._debug("    - not a router we know about")
            return

        ###TODO
        # existing_router_info.status = status
        # if _debug:
        #     RouterInfoCache._debug("    - status updated")

    def delete_router_info(
        self,
        snet: int,
        address: Optional[Address] = None,
        dnets: Optional[List[int]] = None,
    ) -> None:
        if _debug:
            RouterInfoCache._debug("delete_router_info %r %r %r", dnets)

        if (address is None) and (dnets is None):
            raise RuntimeError("inconsistent parameters")

        # remove the dnets from a router or the whole router
        if address is not None:
            router_info = self.routers.get(snet, {}).get(address, None)
            if not router_info:
                if _debug:
                    RouterInfoCache._debug("    - no route info")
            else:
                for dnet in dnets or router_info.dnets:
                    del self.path_info[(snet, dnet)]
                    if _debug:
                        RouterInfoCache._debug(
                            "    - del path: %r -> %r via %r",
                            snet,
                            dnet,
                            router_info.address,
                        )
                del self.routers[snet][address]
            return

        # look for routers to the dnets
        other_routers = set()
        for dnet in dnets:  # type: ignore[union-attr]
            other_router = self.path_info.get((snet, dnet), None)
            if other_router:  ###TODO: and (other_router is not existing_router_info):
                other_routers.add(other_router)

        # remove the dnets from other router(s) and paths
        for router_info in other_routers:
            for dnet in dnets:  # type: ignore[union-attr]
                if dnet in router_info.dnets:
                    del router_info.dnets[dnet]
                    del self.path_info[(snet, dnet)]
                    if _debug:
                        RouterInfoCache._debug(
                            "    - del path: %r -> %r via %r",
                            snet,
                            dnet,
                            router_info.address,
                        )
            if not router_info.dnets:
                del self.routers[snet][router_info.address]
                if _debug:
                    RouterInfoCache._debug(
                        "    - no dnets: %r via %r", snet, router_info.address
                    )

    def update_source_network(self, old_snet: int, new_snet: int) -> None:
        if _debug:
            RouterInfoCache._debug("update_source_network %r %r", old_snet, new_snet)

        if old_snet not in self.routers:
            if _debug:
                RouterInfoCache._debug(
                    "    - no router references: %r", list(self.routers.keys())
                )
            return

        # move the router info records to the new net
        snet_routers = self.routers[new_snet] = self.routers.pop(old_snet)

        # update the paths
        for address, router_info in snet_routers.items():
            for dnet in router_info.dnets:
                self.path_info[(new_snet, dnet)] = self.path_info.pop((old_snet, dnet))


#
#   NetworkAdapter
#


@bacpypes_debugging
class NetworkAdapter(Client[PDU], DebugContents):
    _debug: Callable[..., None]
    _debug_contents = (
        "adapterSAP-",
        "adapterNet",
        "adapterAddr",
        "adapterNetConfigured",
    )

    adapterSAP: NetworkServiceAccessPoint
    adapterNet: Optional[int]
    adapterAddr: Optional[Address]
    adapterNetConfigured: int  # NetworkNumberQuality

    def __init__(
        self,
        sap: NetworkServiceAccessPoint,
        net: Optional[int] = None,
        addr: Optional[Address] = None,
        cid=None,
    ) -> None:
        if _debug:
            NetworkAdapter._debug("__init__ %s %r %r cid=%r", sap, net, addr, cid)
        Client.__init__(self, cid)

        self.adapterSAP = sap
        self.adapterNet = net
        self.adapterAddr = addr

        # record if this was configured
        if net is None:
            self.adapterNetConfigured = NetworkNumberQuality.unknown
        else:
            self.adapterNetConfigured = NetworkNumberQuality.configured

    async def confirmation(self, pdu: PDU) -> None:
        """Decode upstream PDUs and pass them up to the service access point."""
        if _debug:
            NetworkAdapter._debug("confirmation %r (net=%r)", pdu, self.adapterNet)

        # decode as an NPDU
        npdu = NPDU.decode(pdu)

        # if this is a network layer message, find the subclass and let it
        # decode the message
        if npdu.npduNetMessage is not None:
            try:
                npdu_class = npdu_types[npdu.npduNetMessage]
            except KeyError:
                raise RuntimeError(f"unrecognized NPDU type: {npdu.npduNetMessage}")
            if _debug:
                NetworkAdapter._debug("    - npdu_class: %r", npdu_class)

            # ask the class to decode the rest of the PDU
            xpdu = npdu_class.decode(npdu)
            NPCI.update(xpdu, npdu)

            # swap in the new one
            npdu = xpdu
        if _debug:
            NetworkAdapter._debug("    - npdu: %r", npdu)

        # send it to the service access point
        await self.adapterSAP.process_npdu(self, npdu)

    async def process_npdu(self, npdu: NPDU) -> None:
        """Encode NPDUs from the service access point and send them downstream."""
        if _debug:
            NetworkAdapter._debug("process_npdu %r (net=%r)", npdu, self.adapterNet)

        # encode it as a PDU
        pdu = npdu.encode()
        if _debug:
            NetworkAdapter._debug("    - pdu: %r", pdu)

        # send it downstream
        await self.request(pdu)

    def EstablishConnectionToNetwork(self, net):
        pass

    def DisconnectConnectionToNetwork(self, net):
        pass


#
#   NetworkServiceAccessPoint
#


@bacpypes_debugging
class NetworkServiceAccessPoint(ServiceAccessPoint, Server[PDU], DebugContents):
    _debug: Callable[..., None]
    _warning: Callable[..., None]
    _debug_contents = (
        "adapters++",
        "local_adapter-",
        "router_info_cache",
    )

    adapters: Dict[Union[int, None], NetworkAdapter]
    local_adapter: Optional[NetworkAdapter]
    router_info_cache: RouterInfoCache

    def __init__(
        self,
        router_info_cache: Optional[RouterInfoCache] = None,
        sap: Optional[str] = None,
        sid: Optional[str] = None,
    ) -> None:
        if _debug:
            NetworkServiceAccessPoint._debug("__init__ sap=%r sid=%r", sap, sid)
        ServiceAccessPoint.__init__(self, sap)
        Server.__init__(self, sid)

        # map of directly connected networks
        self.adapters = {}  # net -> NetworkAdapter

        # use the provided cache or make a default one
        self.router_info_cache = router_info_cache or RouterInfoCache()

        # set when bind() is called
        self.local_adapter = None

    def bind(
        self,
        server: Server[PDU],
        net: Optional[int] = None,
        address: Optional[Address] = None,
    ) -> None:
        """Create a network adapter object and bind.

        bind(s, None, None)
            Called for simple applications, local network unknown, no specific
            address, APDUs sent upstream

        bind(s, net, None)
            Called for routers, bind to the network, (optionally?) drop APDUs

        bind(s, None, address)
            Called for applications or routers, bind to the network (to be
            discovered), send up APDUs with a matching address

        bind(s, net, address)
            Called for applications or routers, bind to the network, send up
            APDUs with a matching address.
        """
        if _debug:
            NetworkServiceAccessPoint._debug(
                "bind %r net=%r address=%r", server, net, address
            )

        # make sure this hasn't already been called with this network
        if net in self.adapters:
            raise RuntimeError("already bound: %r" % (net,))

        # create an adapter object, add it to our map
        adapter = NetworkAdapter(self, net, address)
        self.adapters[net] = adapter
        if _debug:
            NetworkServiceAccessPoint._debug("    - adapter: %r, %r", net, adapter)

        # if the address was given, make it the "local" one
        if address:
            if self.local_adapter:
                if _debug:
                    NetworkServiceAccessPoint._debug(
                        "    - local adapter already set: %s", self.local_adapter
                    )
            else:
                if _debug:
                    NetworkServiceAccessPoint._debug("    - setting local adapter")
                self.local_adapter = adapter

        # if the local adapter isn't set yet, make it the first one, and can
        # be overridden by a subsequent call if the address is specified
        if not self.local_adapter:
            if _debug:
                NetworkServiceAccessPoint._debug("    - default local adapter")
            self.local_adapter = adapter

        if not self.local_adapter.adapterAddr:
            if _debug:
                NetworkServiceAccessPoint._debug("    - no local address")

        # bind to the server
        bind(adapter, server)

    # -----

    def update_router_references(
        self, snet: int, address: Address, dnets: List[int]
    ) -> None:
        """Update references to routers."""
        if _debug:
            NetworkServiceAccessPoint._debug(
                "update_router_references %r %r %r", snet, address, dnets
            )

        # see if we have an adapter for the snet
        if snet not in self.adapters:
            raise RuntimeError("no adapter for network: %d" % (snet,))

        # pass this along to the cache
        self.router_info_cache.update_router_info(snet, address, dnets)

    def delete_router_references(
        self,
        snet: int,
        address: Optional[Address] = None,
        dnets: Optional[List[int]] = None,
    ) -> None:
        """Delete references to routers/networks."""
        if _debug:
            NetworkServiceAccessPoint._debug(
                "delete_router_references %r %r %r", snet, address, dnets
            )

        # see if we have an adapter for the snet
        if snet not in self.adapters:
            raise RuntimeError("no adapter for network: %d" % (snet,))

        # pass this along to the cache
        self.router_info_cache.delete_router_info(snet, address, dnets)

    # -----

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            NetworkServiceAccessPoint._debug("indication %r", pdu)

        # make sure our configuration is OK
        if not self.adapters:
            raise ConfigurationError("no adapters")
        if not self.serviceElement:
            raise ConfigurationError("no service element")

        # reference the service element
        nse = cast(NetworkServiceElement, self.serviceElement)
        if _debug:
            NetworkServiceAccessPoint._debug("    - nse: %r", nse)

        # get the local adapter
        local_adapter = self.local_adapter
        if _debug:
            NetworkServiceAccessPoint._debug("    - local_adapter: %r", local_adapter)

        # start with an NPDU, start with the provided PCI data
        npdu = NPDU(pdu.pduData, user_data=pdu.pduUserData)
        PCI.update(npdu, pdu)
        if _debug:
            NetworkServiceAccessPoint._debug("    - npdu: %r", npdu)
        assert npdu.pduDestination

        # the hop count always starts out big
        npdu.npduHopCount = 255

        # if this is route aware, use it for the destination
        if settings.route_aware and npdu.pduDestination.addrRoute:
            # always a local station for now, in theory this could also be
            # a local braodcast address, remote station, or remote broadcast
            # but that is not supported by the patterns
            assert npdu.pduDestination.addrRoute.addrType == Address.localStationAddr
            if _debug:
                NetworkServiceAccessPoint._debug(
                    "    - routed: %r", npdu.pduDestination.addrRoute
                )

            if npdu.pduDestination.addrType in (
                Address.remoteStationAddr,
                Address.remoteBroadcastAddr,
                Address.globalBroadcastAddr,
            ):
                if _debug:
                    NetworkServiceAccessPoint._debug(
                        "    - continue DADR: %r", npdu.pduDestination
                    )
                npdu.npduDADR = npdu.pduDestination

            npdu.pduDestination = npdu.pduDestination.addrRoute
            if local_adapter:
                await local_adapter.process_npdu(npdu)
            return

        # local stations given to local adapter
        if npdu.pduDestination.addrType == Address.localStationAddr:
            if local_adapter:
                await local_adapter.process_npdu(npdu)
            return

        # local broadcast given to local adapter
        if npdu.pduDestination.addrType == Address.localBroadcastAddr:
            if local_adapter:
                await local_adapter.process_npdu(npdu)
            return

        # global broadcast
        if npdu.pduDestination.addrType == Address.globalBroadcastAddr:
            # set the destination
            npdu.pduDestination = LocalBroadcast()
            npdu.npduDADR = pdu.pduDestination

            # send it to all of connected adapters
            for xadapter in self.adapters.values():
                await xadapter.process_npdu(npdu)
            return

        # remote broadcast
        if (npdu.pduDestination.addrType != Address.remoteBroadcastAddr) and (
            npdu.pduDestination.addrType != Address.remoteStationAddr
        ):
            raise RuntimeError(
                "invalid destination address type: %s" % (npdu.pduDestination.addrType,)
            )

        dnet = npdu.pduDestination.addrNet
        if _debug:
            NetworkServiceAccessPoint._debug("    - dnet: %r", dnet)

        # if the network matches the local adapter it's local
        if local_adapter and (dnet == local_adapter.adapterNet):
            if npdu.pduDestination.addrType == Address.remoteStationAddr:
                if _debug:
                    NetworkServiceAccessPoint._debug(
                        "    - mapping remote station to local station"
                    )
                npdu.pduDestination = LocalStation(npdu.pduDestination.addrAddr)
            elif npdu.pduDestination.addrType == Address.remoteBroadcastAddr:
                if _debug:
                    NetworkServiceAccessPoint._debug(
                        "    - mapping remote broadcast to local broadcast"
                    )
                npdu.pduDestination = LocalBroadcast()
            else:
                raise RuntimeError("addressing problem")

            await local_adapter.process_npdu(npdu)
            return

        # get it ready to send when the path is found
        npdu.pduDestination = None
        npdu.npduDADR = pdu.pduDestination
        if _debug:
            NetworkServiceAccessPoint._debug(
                "    - look for routing information: %r", self.router_info_cache
            )

        # look for routing information from the network of one of our
        # adapters to the destination network
        router_info = None
        for snet, snet_adapter in self.adapters.items():
            router_info = self.router_info_cache.get_router_info(snet, dnet)
            if router_info:
                break

        # if there is info, we have a path
        if router_info:
            if _debug:
                NetworkServiceAccessPoint._debug(
                    "    - router_info found: %r", router_info
                )

            # check the path status
            dnet_status = router_info.dnets[dnet]
            if _debug:
                NetworkServiceAccessPoint._debug("    - dnet_status: %r", dnet_status)

            # fix the destination and send it
            npdu.pduDestination = router_info.address
            await snet_adapter.process_npdu(npdu)

        else:
            if _debug:
                NetworkServiceAccessPoint._debug("    - look for the router")

            result_list = await nse.who_is_router_to_network(network=dnet)
            if not result_list:
                if _debug:
                    NetworkServiceAccessPoint._debug("    - no router responded")
                raise UnknownRoute()
            if len(result_list) > 1:
                if _debug:
                    NetworkServiceAccessPoint._debug(
                        "    - more than one router responded"
                    )
                raise UnknownRoute()

            router_adapter, i_am_router_to_network = result_list[0]
            if _debug:
                NetworkServiceAccessPoint._debug(
                    "    - found path: %r, %r",
                    router_adapter,
                    i_am_router_to_network.pduSource,
                )

            # fix the destination and send it
            npdu.pduDestination = i_am_router_to_network.pduSource
            await router_adapter.process_npdu(npdu)

    async def process_npdu(self, adapter: NetworkAdapter, npdu: NPDU) -> None:
        if _debug:
            NetworkServiceAccessPoint._debug("process_npdu %r %r", adapter, npdu)

        # make sure our configuration is OK
        if not self.adapters:
            raise ConfigurationError("no adapters")
        if not self.serviceElement:
            raise ConfigurationError("no service element")

        # reference the service element
        nse = cast(NetworkServiceElement, self.serviceElement)
        if _debug:
            NetworkServiceAccessPoint._debug("    - nse: %r", nse)

        # check for source routing
        if npdu.npduSADR and (npdu.npduSADR.addrType != Address.nullAddr):
            if _debug:
                NetworkServiceAccessPoint._debug("    - check source path")

            # see if this is attempting to spoof a directly connected network
            snet = npdu.npduSADR.addrNet
            if snet in self.adapters:
                NetworkServiceAccessPoint._warning("    - path error (1)")
                return

            # pass this new path along to the cache
            self.router_info_cache.update_router_info(
                adapter.adapterNet,
                cast(Address, npdu.pduSource),
                [snet],  # type: ignore[list-item]
            )

        # check for destination routing
        if (not npdu.npduDADR) or (npdu.npduDADR.addrType == Address.nullAddr):
            if _debug:
                NetworkServiceAccessPoint._debug("    - no DADR")

            processLocally = (adapter is self.local_adapter) or (
                npdu.npduNetMessage is not None
            )
            forwardMessage = False

        elif npdu.npduDADR.addrType == Address.remoteBroadcastAddr:
            if _debug:
                NetworkServiceAccessPoint._debug("    - DADR is remote broadcast")
            assert self.local_adapter is not None

            if npdu.npduDADR.addrNet == adapter.adapterNet:
                NetworkServiceAccessPoint._warning("    - path error (2)")
                return

            processLocally = npdu.npduDADR.addrNet == self.local_adapter.adapterNet
            forwardMessage = True

        elif npdu.npduDADR.addrType == Address.remoteStationAddr:
            if _debug:
                NetworkServiceAccessPoint._debug("    - DADR is remote station")
            assert self.local_adapter is not None

            if npdu.npduDADR.addrNet == adapter.adapterNet:
                NetworkServiceAccessPoint._warning("    - path error (3)")
                return

            processLocally = (
                npdu.npduDADR.addrNet == self.local_adapter.adapterNet
            ) and (
                npdu.npduDADR.addrAddr == self.local_adapter.adapterAddr.addrAddr  # type: ignore[union-attr]
            )
            forwardMessage = not processLocally

        elif npdu.npduDADR.addrType == Address.globalBroadcastAddr:
            if _debug:
                NetworkServiceAccessPoint._debug("    - DADR is global broadcast")

            processLocally = True
            forwardMessage = True

        else:
            NetworkServiceAccessPoint._warning(
                "invalid destination address type: %s", npdu.npduDADR.addrType
            )
            return

        if _debug:
            NetworkServiceAccessPoint._debug("    - processLocally: %r", processLocally)
            NetworkServiceAccessPoint._debug("    - forwardMessage: %r", forwardMessage)

        # application or network layer message
        if npdu.npduNetMessage is None:
            if _debug:
                NetworkServiceAccessPoint._debug("    - application layer message")

            if processLocally and self.serverPeer:
                if _debug:
                    NetworkServiceAccessPoint._debug("    - processing PDU locally")
                assert self.local_adapter is not None

                # start with normal PDU
                pdu = PDU(npdu.pduData, user_data=npdu.pduUserData)
                PCI.update(pdu, npdu)
                if _debug:
                    NetworkServiceAccessPoint._debug("    - pdu: %r", pdu)

                # see if it needs to look routed
                if (len(self.adapters) > 1) and (adapter != self.local_adapter):
                    # combine the source address
                    if not npdu.npduSADR:
                        pdu.pduSource = RemoteStation(
                            adapter.adapterNet,  # type: ignore[arg-type]
                            npdu.pduSource.addrAddr,  # type: ignore[union-attr]
                        )
                    else:
                        pdu.pduSource = npdu.npduSADR
                    if settings.route_aware:
                        pdu.pduSource.addrRoute = npdu.pduSource

                    # map the destination
                    if not npdu.npduDADR:
                        pdu.pduDestination = self.local_adapter.adapterAddr
                    elif npdu.npduDADR.addrType == Address.globalBroadcastAddr:
                        pdu.pduDestination = GlobalBroadcast()
                    elif npdu.npduDADR.addrType == Address.remoteBroadcastAddr:
                        pdu.pduDestination = LocalBroadcast()
                    else:
                        pdu.pduDestination = self.local_adapter.adapterAddr
                else:
                    # combine the source address
                    if npdu.npduSADR:
                        pdu.pduSource = npdu.npduSADR
                        if settings.route_aware:
                            if _debug:
                                NetworkServiceAccessPoint._debug("    - adding route")
                            pdu.pduSource.addrRoute = npdu.pduSource
                    else:
                        pdu.pduSource = npdu.pduSource

                    # pass along global broadcast
                    if (
                        npdu.npduDADR
                        and npdu.npduDADR.addrType == Address.globalBroadcastAddr
                    ):
                        pdu.pduDestination = GlobalBroadcast()
                    else:
                        pdu.pduDestination = npdu.pduDestination
                if _debug:
                    NetworkServiceAccessPoint._debug(
                        "    - pdu.pduSource: %r", pdu.pduSource
                    )
                    NetworkServiceAccessPoint._debug(
                        "    - pdu.pduDestination: %r", pdu.pduDestination
                    )

                # pass upstream to the application layer
                await self.response(pdu)

        else:
            if _debug:
                NetworkServiceAccessPoint._debug("    - network layer message")

            if processLocally:
                if npdu.npduNetMessage not in npdu_types:
                    if _debug:
                        NetworkServiceAccessPoint._debug(
                            "    - unknown npdu type: %r", npdu.npduNetMessage
                        )
                    return

                if _debug:
                    NetworkServiceAccessPoint._debug("    - processing NPDU locally")

                # pass to the service element
                await self.sap_request(adapter, npdu)

        # might not need to forward this to other devices
        if not forwardMessage:
            if _debug:
                NetworkServiceAccessPoint._debug("    - no forwarding")
            return

        # make sure we're really a router
        if len(self.adapters) == 1:
            if _debug:
                NetworkServiceAccessPoint._debug("    - not a router")
            return

        # make sure it hasn't looped
        if npdu.npduHopCount == 0:
            if _debug:
                NetworkServiceAccessPoint._debug("    - no more hops")
            return

        # build a new NPDU to send to other adapters
        newpdu = _deepcopy(npdu)

        # clear out the source and destination
        newpdu.pduSource = None
        newpdu.pduDestination = None

        # decrease the hop count
        newpdu.npduHopCount -= 1

        # set the source address
        if not npdu.npduSADR:
            newpdu.npduSADR = RemoteStation(
                adapter.adapterNet,  # type: ignore[arg-type]
                npdu.pduSource.addrAddr,  # type: ignore[union-attr]
            )
        else:
            newpdu.npduSADR = npdu.npduSADR
        assert npdu.npduDADR is not None

        # if this is a broadcast it goes everywhere
        if npdu.npduDADR.addrType == Address.globalBroadcastAddr:
            if _debug:
                NetworkServiceAccessPoint._debug("    - global broadcasting")
            newpdu.pduDestination = LocalBroadcast()

            for xadapter in self.adapters.values():
                if xadapter is not adapter:
                    await xadapter.process_npdu(_deepcopy(newpdu))
            return

        if (npdu.npduDADR.addrType == Address.remoteBroadcastAddr) or (
            npdu.npduDADR.addrType == Address.remoteStationAddr
        ):
            if _debug:
                NetworkServiceAccessPoint._debug("    - remote station/broadcast")
            dnet = npdu.npduDADR.addrNet
            assert dnet is not None

            # see if this a locally connected network
            if dnet in self.adapters:
                xadapter = self.adapters[dnet]
                if xadapter is adapter:
                    if _debug:
                        NetworkServiceAccessPoint._debug("    - path error (4)")
                    return
                if _debug:
                    NetworkServiceAccessPoint._debug(
                        "    - found path via %r", xadapter
                    )

                # if this was a remote broadcast, it's now a local one
                if npdu.npduDADR.addrType == Address.remoteBroadcastAddr:
                    newpdu.pduDestination = LocalBroadcast()
                else:
                    newpdu.pduDestination = LocalStation(
                        npdu.npduDADR.addrAddr,  # type: ignore[arg-type]
                    )

                # last leg in routing
                newpdu.npduDADR = None

                # send the packet downstream
                await xadapter.process_npdu(_deepcopy(newpdu))
                return

            # look for routing information from the network of one of our
            # adapters to the destination network
            router_info = None
            for snet, snet_adapter in self.adapters.items():
                router_info = self.router_info_cache.get_router_info(snet, dnet)
                if router_info:
                    router_adapter = snet_adapter
                    router_address = router_info.address
                    break

            # no path, look for one
            if not router_info:
                if _debug:
                    NetworkServiceAccessPoint._debug("    - look for the router")

                result_list = await nse.who_is_router_to_network(network=dnet)
                if not result_list:
                    raise UnknownRoute()
                if len(result_list) > 1:
                    raise UnknownRoute()

                router_adapter, router_address = (
                    result_list[0],
                    result_list[0].pduSource,
                )

            if _debug:
                NetworkServiceAccessPoint._debug(
                    "    - found path: %r, %r", router_adapter, router_address
                )

            # the destination is the address of the router
            newpdu.pduDestination = router_address

            # send the packet downstream
            await router_adapter.process_npdu(_deepcopy(newpdu))

        if _debug:
            NetworkServiceAccessPoint._debug("    - bad DADR: %r", npdu.npduDADR)

    async def sap_indication(self, adapter: NetworkAdapter, npdu: NPDU) -> None:  # type: ignore[override]
        if _debug:
            NetworkServiceAccessPoint._debug("sap_indication %r %r", adapter, npdu)

        # tell the adapter to process the NPDU
        await adapter.process_npdu(npdu)

    async def sap_confirmation(self, adapter: NetworkAdapter, npdu: NPDU) -> None:  # type: ignore[override]
        if _debug:
            NetworkServiceAccessPoint._debug("sap_confirmation %r %r", adapter, npdu)

        # tell the adapter to process the NPDU
        await adapter.process_npdu(npdu)


#
#   NetworkServiceElement
#


@bacpypes_debugging
class WhoIsRouterToNetworkFuture:
    """
    Instances of this class are used to track Who-Is-Router-To-Network requests
    and responses.
    """

    _debug: Callable[..., None]

    nse: NetworkServiceElement
    adapter: Optional[NetworkAdapter]
    router_address: Optional[Address]
    network: Optional[int]
    future: asyncio.Future

    result_list: List[Tuple[NetworkAdapter, IAmRouterToNetwork]]

    def __init__(
        self,
        nse: NetworkServiceElement,
        adapter: Optional[NetworkAdapter] = None,
        router_address: Optional[Address] = None,
        network: Optional[int] = None,
    ) -> None:
        if _debug:
            WhoIsRouterToNetworkFuture._debug(
                "__init__ %r %r %r %r", nse, adapter, router_address, network
            )

        self.nse = nse
        self.adapter = adapter
        self.router_address = router_address
        self.network = network

        self.result_list = []

        # create a future and add a callback when it is resolved
        self.future = asyncio.Future()
        self.future.add_done_callback(self.who_is_router_to_network_done)
        if _debug:
            WhoIsRouterToNetworkFuture._debug("    - future: %r", self.future)

        # get the loop to schedule a time to stop looking
        loop = asyncio.get_event_loop()
        if _debug:
            WhoIsRouterToNetworkFuture._debug("    - loop time: %r", loop.time())

        # schedule a call
        self._timeout_handle = loop.call_later(
            WHO_IS_ROUTER_TO_NETWORK_TIMEOUT, self.who_is_router_to_network_timeout
        )
        if _debug:
            WhoIsRouterToNetworkFuture._debug(
                "    - _timeout_handle: %r", self._timeout_handle
            )

    def match(self, adapter, npdu: IAmRouterToNetwork) -> None:
        """
        This function is called for each incoming IAmRouterToNetwork to see if
        it matches the criteria.
        """
        if _debug:
            WhoIsRouterToNetworkFuture._debug("match %r", npdu)

        if self.adapter and (adapter != self.adapter):
            return

        if npdu.npduSADR:
            npdu_source = npdu.npduSADR
            npdu_source.addrRoute = npdu.pduSource
        else:
            npdu_source = npdu.pduSource
        if _debug:
            WhoIsRouterToNetworkFuture._debug("    - npdu_source: %r", npdu_source)

        if self.network is not None:
            if self.network in npdu.iartnNetworkList:
                if _debug:
                    WhoIsRouterToNetworkFuture._debug("    - network match")
                self.result_list.append((adapter, npdu))
                self.future.set_result(self.result_list)

        elif not self.router_address:
            if _debug:
                WhoIsRouterToNetworkFuture._debug("    - wildcard match")
            self.result_list.append((adapter, npdu))

        elif npdu_source.match(self.router_address):
            if _debug:
                WhoIsRouterToNetworkFuture._debug("    - address match")
            self.result_list.append((adapter, npdu))

            # if we're looking for a specific response, we found it
            if self.router_address.addrType in (
                Address.localStationAddr,
                Address.remoteStationAddr,
            ):
                if _debug:
                    WhoIsRouterToNetworkFuture._debug("    - request complete")
                self.future.set_result(self.result_list)

        else:
            if _debug:
                WhoIsRouterToNetworkFuture._debug("    - no match")

    def who_is_router_to_network_done(self, future: asyncio.Future) -> None:
        """The future has been completed or canceled."""
        if _debug:
            WhoIsRouterToNetworkFuture._debug(
                "who_is_router_to_network_done %r", future
            )

        # remove ourselves from the pending requests
        self.nse.who_is_router_to_network_futures.remove(self)

        # if the timeout is still scheduled, cancel it
        self._timeout_handle.cancel()

    def who_is_router_to_network_timeout(self):
        """The timeout has elapsed, save the I-Am messages we found in the
        future."""
        if _debug:
            WhoIsRouterToNetworkFuture._debug("who_is_router_to_network_timeout")

        self.future.set_result(self.result_list)


@bacpypes_debugging
class InitializeRoutingTableFuture:
    """
    Instances of this class are used to track Who-Is-Router-To-Network requests
    and responses.
    """

    _debug: Callable[..., None]

    nse: NetworkServiceElement
    adapter: Optional[NetworkAdapter]
    router_address: Optional[Address]
    future: asyncio.Future

    result_list: List[Tuple[NetworkAdapter, InitializeRoutingTableAck]]

    def __init__(
        self,
        nse: NetworkServiceElement,
        adapter: Optional[NetworkAdapter] = None,
        router_address: Optional[Address] = None,
    ) -> None:
        if _debug:
            InitializeRoutingTableFuture._debug(
                "__init__ %r %r %r", nse, adapter, router_address
            )

        self.nse = nse
        self.adapter = adapter
        if router_address and (
            router_address.is_localbroadcast or router_address.is_remotebroadcast
        ):
            router_address = None
        self.router_address = router_address

        self.result_list = []

        # create a future and add a callback when it is resolved
        self.future = asyncio.Future()
        self.future.add_done_callback(self.done)
        if _debug:
            InitializeRoutingTableFuture._debug("    - future: %r", self.future)

        # get the loop to schedule a time to stop looking
        loop = asyncio.get_event_loop()
        if _debug:
            InitializeRoutingTableFuture._debug("    - loop time: %r", loop.time())

        # schedule a call
        self._timeout_handle = loop.call_later(
            INITIALIZE_ROUTING_TABLE_TIMEOUT, self.timeout
        )
        if _debug:
            InitializeRoutingTableFuture._debug(
                "    - _timeout_handle: %r", self._timeout_handle
            )

    def match(self, adapter, npdu: InitializeRoutingTableAck) -> None:
        """
        This function is called for each incoming InitializeRoutingTableAck to
        see if it matches the criteria.
        """
        if _debug:
            InitializeRoutingTableFuture._debug("match %r", npdu)

        if self.adapter and (adapter != self.adapter):
            return

        if npdu.npduSADR:
            npdu_source = npdu.npduSADR
            npdu_source.addrRoute = npdu.pduSource
        else:
            npdu_source = npdu.pduSource
        if _debug:
            InitializeRoutingTableFuture._debug("    - npdu_source: %r", npdu_source)

        if not self.router_address:
            if _debug:
                InitializeRoutingTableFuture._debug("    - wildcard match")
            self.result_list.append((adapter, npdu))

        elif npdu_source.match(self.router_address):
            if _debug:
                InitializeRoutingTableFuture._debug("    - address match")
            self.result_list.append((adapter, npdu))

            # if we're looking for a specific response, we found it
            if self.router_address.addrType in (
                Address.localStationAddr,
                Address.remoteStationAddr,
            ):
                if _debug:
                    InitializeRoutingTableFuture._debug("    - request complete")
                self.future.set_result(self.result_list)

        else:
            if _debug:
                InitializeRoutingTableFuture._debug("    - no match")

    def done(self, future: asyncio.Future) -> None:
        """The future has been completed or canceled."""
        if _debug:
            InitializeRoutingTableFuture._debug("done %r", future)

        # remove ourselves from the pending requests
        self.nse.initialize_routing_table_futures.remove(self)

        # if the timeout is still scheduled, cancel it
        self._timeout_handle.cancel()

    def timeout(self):
        """The timeout has elapsed, save the I-Am messages we found in the
        future."""
        if _debug:
            InitializeRoutingTableFuture._debug("timeout")

        self.future.set_result(self.result_list)


@bacpypes_debugging
class NetworkServiceElement(ApplicationServiceElement, DebugContents):
    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "who_is_router_to_network_futures",
        "router_to_network_resolution",
        "what_is_network_number_resolution",
    )

    _startup_disabled = False
    who_is_router_to_network_futures: List[WhoIsRouterToNetworkFuture]
    initialize_routing_table_futures: List[InitializeRoutingTableFuture]
    what_is_network_number_resolution: Dict[NetworkAdapter, WhatIsNetworkNumberFuture]

    def __init__(self, eid=None):
        if _debug:
            NetworkServiceElement._debug("__init__ eid=%r", eid)
        ApplicationServiceElement.__init__(self, eid)

        # network number is timeout
        self.network_number_is_task = None
        self.who_is_router_to_network_futures = []
        self.initialize_routing_table_futures = []
        self.what_is_network_number_resolution = {}

        # if starting up is enabled defer our startup function
        # if not self._startup_disabled:
        #     deferred(self.startup)

    def startup(self):
        if _debug:
            NetworkServiceElement._debug("startup")

        # reference the service access point
        sap = self.elementService
        if _debug:
            NetworkServiceElement._debug("    - sap: %r", sap)

        # loop through all of the adapters
        for adapter in sap.adapters.values():
            if _debug:
                NetworkServiceElement._debug("    - adapter: %r", adapter)

            if adapter.adapterNet is None:
                if _debug:
                    NetworkServiceElement._debug("    - skipping, unknown net")
                continue
            elif adapter.adapterAddr is None:
                if _debug:
                    NetworkServiceElement._debug("    - skipping, unknown addr")
                continue

            # build a list of reachable networks
            netlist = []

            # loop through the adapters
            for xadapter in sap.adapters.values():
                if xadapter is not adapter:
                    if (xadapter.adapterNet is None) or (xadapter.adapterAddr is None):
                        continue
                    netlist.append(xadapter.adapterNet)

            # skip for an empty list, perhaps they are not yet learned
            if not netlist:
                if _debug:
                    NetworkServiceElement._debug("    - skipping, no netlist")
                continue

            # pass this along to the cache -- on hold #213
            # sap.router_info_cache.update_router_info(adapter.adapterNet, adapter.adapterAddr, netlist)

            # send an announcement
            self.i_am_router_to_network(adapter=adapter, network=netlist)

    async def indication(self, adapter: NetworkAdapter, npdu: NPDU) -> None:  # type: ignore[override]
        if _debug:
            NetworkServiceElement._debug("indication %r %r", adapter, npdu)

        # redirect
        fn = npdu.__class__.__name__
        response = None
        if hasattr(self, fn):
            response = getattr(self, fn)(adapter, npdu)
            if inspect.isawaitable(response):
                response = await response

    async def confirmation(self, adapter: NetworkAdapter, npdu: NPDU) -> None:  # type: ignore[override]
        if _debug:
            NetworkServiceElement._debug("confirmation %r %r", adapter, npdu)

        # redirect
        fn = npdu.__class__.__name__
        response = None
        if hasattr(self, fn):
            response = getattr(self, fn)(adapter, npdu)
            if inspect.isawaitable(response):
                response = await response

    # -----

    def who_is_router_to_network(
        self,
        adapter: Optional[NetworkAdapter] = None,
        destination: Optional[Address] = None,
        network: Optional[int] = None,
    ) -> asyncio.Future:
        if _debug:
            NetworkServiceElement._debug(
                "who_is_router_to_network %r %r %r", adapter, destination, network
            )

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)
        if _debug:
            NetworkServiceElement._debug("    - sap: %r", sap)

        # process a single adapter or all of the adapters
        if adapter is not None:
            adapter_list = [adapter]
        else:
            adapter_list = list(sap.adapters.values())

        # default to local broadcast
        if not destination:
            destination = LocalBroadcast()

        # create a future
        who_is_router_to_network_future = WhoIsRouterToNetworkFuture(
            self, router_address=destination, network=network
        )
        self.who_is_router_to_network_futures.append(who_is_router_to_network_future)

        # build a request
        npdu = WhoIsRouterToNetwork(network)

        # the hop count always starts out big
        npdu.npduHopCount = 255

        # if this is route aware, use it for the destination
        if destination.addrRoute:
            if destination.addrType in (
                Address.remoteStationAddr,
                Address.remoteBroadcastAddr,
                Address.globalBroadcastAddr,
            ):
                if _debug:
                    NetworkServiceElement._debug("    - continue DADR")
                npdu.npduDADR = destination
            npdu.pduDestination = destination.addrRoute

        # local station, local broadcast
        elif destination.addrType in (
            Address.localStationAddr,
            Address.localBroadcastAddr,
        ):
            npdu.pduDestination = destination

        # global broadcast
        elif destination.addrType == Address.globalBroadcastAddr:
            # set the destination
            npdu.pduDestination = LocalBroadcast()
            npdu.npduDADR = destination

        # remote broadcast
        elif destination.addrType in (
            Address.remoteStationAddr,
            Address.remoteBroadcastAddr,
        ):
            # TODO if a specific adapter wasn't provided, look to see if the
            # "remote" network destination.addrNet is actually a directly
            # connected network
            raise RuntimeError("use route-aware for remote station or remote broadcast")
        if _debug:
            NetworkServiceElement._debug("    - npdu: %r", npdu)

        # loop through all of the adapters
        for adapter in adapter_list:
            # create a task to send it
            asyncio.create_task(self.request(adapter, npdu))

        return who_is_router_to_network_future.future

    async def i_am_router_to_network(
        self,
        adapter: Optional[NetworkAdapter] = None,
        destination: Optional[Address] = None,
        network: Optional[int] = None,
    ) -> None:
        if _debug:
            NetworkServiceElement._debug(
                "i_am_router_to_network %r %r %r", adapter, destination, network
            )

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)
        if _debug:
            NetworkServiceElement._debug("    - sap: %r", sap)

        # if we're not a router, trouble
        if len(sap.adapters) == 1:
            raise RuntimeError("not a router")

        if adapter is not None:
            if destination is None:
                destination = LocalBroadcast()
            elif destination.addrType in (
                Address.localStationAddr,
                Address.localBroadcastAddr,
            ):
                pass
            elif destination.addrType == Address.remoteStationAddr:
                if destination.addrNet != adapter.adapterNet:
                    raise ValueError(
                        "invalid address, remote station for a different adapter"
                    )
                destination = LocalStation(destination.addrAddr)  # type: ignore[arg-type]
            elif destination.addrType == Address.remoteBroadcastAddr:
                if destination.addrNet != adapter.adapterNet:
                    raise ValueError(
                        "invalid address, remote broadcast for a different adapter"
                    )
                destination = LocalBroadcast()
            else:
                raise TypeError("invalid destination address")
        else:
            if destination is None:
                destination = LocalBroadcast()
            elif destination.addrType == Address.localStationAddr:
                raise ValueError("ambiguous destination")
            elif destination.addrType == Address.localBroadcastAddr:
                pass
            elif destination.addrType == Address.remoteStationAddr:
                if destination.addrNet not in sap.adapters:
                    raise ValueError("invalid address, no network for remote station")
                adapter = sap.adapters[destination.addrNet]
                destination = LocalStation(destination.addrAddr)  # type: ignore[arg-type]
            elif destination.addrType == Address.remoteBroadcastAddr:
                if destination.addrNet not in sap.adapters:
                    raise ValueError("invalid address, no network for remote broadcast")
                adapter = sap.adapters[destination.addrNet]
                destination = LocalBroadcast()
            else:
                raise TypeError("invalid destination address")
        if _debug:
            NetworkServiceElement._debug(
                "    - adapter, destination, network: %r, %r, %r",
                adapter,
                destination,
                network,
            )

        # process a single adapter or all of the adapters
        if adapter is not None:
            adapter_list = [adapter]
        else:
            adapter_list = list(sap.adapters.values())

        # loop through all of the adapters
        for adapter in adapter_list:
            # build a list of reachable networks
            netlist: List[int] = []

            # loop through the adapters
            for xadapter in sap.adapters.values():
                if xadapter is not adapter:
                    netlist.append(xadapter.adapterNet)  # type: ignore [arg-type]
                    ###TODO add the other reachable networks

            if network is None:
                pass
            elif isinstance(network, int):
                if network not in netlist:
                    continue
                netlist = [network]
            elif isinstance(network, list):
                netlist = [net for net in netlist if net in network]

            # build a response
            iamrtn = IAmRouterToNetwork(netlist, destination=destination)
            if _debug:
                NetworkServiceElement._debug(
                    "    - adapter, iamrtn: %r, %r", adapter, iamrtn
                )

            # send it back
            await self.request(adapter, iamrtn)

    def what_is_network_number(
        self,
        adapter: Optional[NetworkAdapter] = None,
        destination: Optional[Address] = None,
    ) -> asyncio.Future:
        """
        Request the network number, optionally for a specific adapter, and if
        adapter is provided then send the request to a specific address.
        """
        if _debug:
            NetworkServiceElement._debug(
                "what_is_network_number %r %r", adapter, destination
            )

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)

        adapter_list: List[NetworkAdapter] = list(sap.adapters.values())
        if not adapter_list:
            raise RuntimeError("no adapters")

        # check the parameters
        if adapter:
            if adapter not in adapter_list:
                raise RuntimeError(f"not an adapter: {adapter}")
        else:
            if destination and len(adapter_list) > 1:
                raise RuntimeError("more than one adapter")

        # build a request
        request = WhatIsNetworkNumber(destination=LocalBroadcast())
        if _debug:
            NetworkServiceElement._debug("    - request: %r", request)

        # check for a specific adapter and maybe a specific address
        if adapter and destination:
            request.pduDestination = destination
            adapter_list = [adapter]
        if _debug:
            NetworkServiceElement._debug("    - adapter_list: %r", adapter_list)

        # create a future
        future = WhatIsNetworkNumberFuture()
        if len(adapter_list) > 1:
            # asking for multiple adapters at the same time will send the
            # requests out but will not stash the future to be resolved
            future.set_result(-1)
        else:
            # store this future to be resolved
            self.what_is_network_number_resolution[adapter_list[0]] = future

            # add a callback when the request is resolved or canceled (timeout)
            future.add_done_callback(self._resolve_what_is_network_number)

        # send it to the adapter(s)
        for xadapter in adapter_list:
            # create a task to send it
            asyncio.create_task(self.request(xadapter, request))

        return future

    def _resolve_what_is_network_number(self, future) -> None:
        """
        This private callback function clears the reference to the pending
        future for resolving what_is_network_number() calls.
        """
        if _debug:
            NetworkServiceElement._debug("_resolve_what_is_network_number %r", future)

        for adapter, pending_future in self.what_is_network_number_resolution.items():
            if future is pending_future:
                if _debug:
                    NetworkServiceElement._debug("    - found it")
                del self.what_is_network_number_resolution[adapter]
                break
        else:
            if _debug:
                NetworkServiceElement._debug("    - future not found")

    async def network_number_is(self, adapter=None) -> None:
        """
        This function initiates a Network-Number-Is broadcast to a specific
        adapter or to all of the adapters.  If the request is for all of the
        adapters, only those that have the network number 'configured' will
        be broadcast.
        """
        if _debug:
            NetworkServiceElement._debug("network_number_is %r", adapter)

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)

        # specific adapter, or all configured adapters
        if adapter is not None:
            adapter_list = [adapter]
        else:
            # send to adapters we are configured to know
            adapter_list = []
            for xadapter in sap.adapters.values():
                if (xadapter.adapterNet is not None) and (
                    xadapter.adapterNetConfigured == NetworkNumberQuality.configured
                ):
                    adapter_list.append(xadapter)
        if _debug:
            NetworkServiceElement._debug("    - adapter_list: %r", adapter_list)

        # loop through the adapter(s)
        for xadapter in adapter_list:
            if xadapter.adapterNet is None:
                if _debug:
                    NetworkServiceElement._debug("    - unknown network: %r", xadapter)
                continue

            # build a broadcast annoucement
            nni = NetworkNumberIs(
                net=xadapter.adapterNet,
                flag=xadapter.adapterNetConfigured,
                destination=LocalBroadcast(),
            )
            if _debug:
                NetworkServiceElement._debug("    - nni: %r", nni)

            # send it to the adapter
            await self.request(xadapter, nni)

    def initialize_routing_table(
        self,
        adapter: Optional[NetworkAdapter] = None,
        destination: Optional[Address] = None,
    ) -> asyncio.Future:
        """
        Send an "empty" Initialize-Routing-Table message to a device, return
        a list of (adapter, InitializeRoutingTableAck) tuples.
        """
        if _debug:
            NetworkServiceElement._debug(
                "initialize_routing_table %r %r", adapter, destination
            )

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)
        if _debug:
            NetworkServiceElement._debug("    - sap: %r", sap)

        # process a single adapter or all of the adapters
        if adapter is not None:
            adapter_list = [adapter]
        else:
            adapter_list = list(sap.adapters.values())

        # default to local broadcast
        if not destination:
            destination = LocalBroadcast()

        # create a future
        initialize_routing_table_future = InitializeRoutingTableFuture(
            self, adapter, destination
        )
        if _debug:
            NetworkServiceElement._debug(
                "    - initialize_routing_table_future: %r",
                initialize_routing_table_future,
            )
        self.initialize_routing_table_futures.append(initialize_routing_table_future)

        # build a request
        npdu = InitializeRoutingTable([])

        # the hop count always starts out big
        npdu.npduHopCount = 255

        # if this is route aware, use it for the destination
        if destination.addrRoute:
            if destination.addrType in (
                Address.remoteStationAddr,
                Address.remoteBroadcastAddr,
                Address.globalBroadcastAddr,
            ):
                if _debug:
                    NetworkServiceElement._debug("    - continue DADR")
                npdu.npduDADR = destination
            npdu.pduDestination = destination.addrRoute

        # local station, local broadcast
        elif destination.addrType in (
            Address.localStationAddr,
            Address.localBroadcastAddr,
        ):
            npdu.pduDestination = destination

        # global broadcast
        elif destination.addrType == Address.globalBroadcastAddr:
            # set the destination
            npdu.pduDestination = LocalBroadcast()
            npdu.npduDADR = destination

        # remote broadcast
        elif destination.addrType in (
            Address.remoteStationAddr,
            Address.remoteBroadcastAddr,
        ):
            raise RuntimeError("use route-aware for remote station or remote broadcast")
        if _debug:
            NetworkServiceElement._debug("    - npdu: %r", npdu)

        # loop through all of the adapters
        for adapter in adapter_list:
            # create a task to send it
            asyncio.create_task(self.request(adapter, npdu))

        return initialize_routing_table_future.future

    # -----

    async def WhoIsRouterToNetwork(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug("WhoIsRouterToNetwork %r %r", adapter, npdu)

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)
        if _debug:
            NetworkServiceElement._debug("    - sap: %r", sap)

        # if we're not a router, skip it
        if len(sap.adapters) == 1:
            if _debug:
                NetworkServiceElement._debug("    - not a router")
            return

        if npdu.wirtnNetwork is None:
            # requesting all networks
            if _debug:
                NetworkServiceElement._debug("    - requesting all networks")

            # build a list of reachable networks
            netlist = []

            # loop through the adapters
            for xadapter in sap.adapters.values():
                if xadapter is adapter:
                    continue

                # add the direct network
                netlist.append(xadapter.adapterNet)

                ###TODO add the other reachable networks?

            if netlist:
                if _debug:
                    NetworkServiceElement._debug("    - found these: %r", netlist)

                # build a response
                iamrtn = IAmRouterToNetwork(netlist, user_data=npdu.pduUserData)
                iamrtn.pduDestination = npdu.pduSource

                # send it back
                await self.response(adapter, iamrtn)

        else:
            # requesting a specific network
            if _debug:
                NetworkServiceElement._debug(
                    "    - requesting specific network: %r", npdu.wirtnNetwork
                )
            dnet = npdu.wirtnNetwork

            # check the directly connected networks
            if dnet in sap.adapters:
                if _debug:
                    NetworkServiceElement._debug("    - directly connected")

                if sap.adapters[dnet] is adapter:
                    if _debug:
                        NetworkServiceElement._debug("    - same network")
                    return

                # build a response
                iamrtn = IAmRouterToNetwork(
                    [dnet], user_data=npdu.pduUserData, destination=npdu.pduSource
                )

                # send it back
                await self.response(adapter, iamrtn)
                return

            # look for routing information from the network of one of our
            # adapters to the destination network
            router_info = None
            for snet, snet_adapter in sap.adapters.items():
                router_info = sap.router_info_cache.get_router_info(snet, dnet)
                if router_info:
                    break

            # found a path
            if router_info:
                if _debug:
                    NetworkServiceElement._debug("    - router found: %r", router_info)

                if snet_adapter is adapter:
                    if _debug:
                        NetworkServiceElement._debug("    - same network")
                    return

                # build a response
                iamrtn = IAmRouterToNetwork([dnet], user_data=npdu.pduUserData)
                iamrtn.pduDestination = npdu.pduSource

                # send it back
                await self.response(adapter, iamrtn)

            else:
                if _debug:
                    NetworkServiceElement._debug("    - forwarding to other adapters")

                # build a request
                whoisrtn = WhoIsRouterToNetwork(dnet, user_data=npdu.pduUserData)
                whoisrtn.pduDestination = LocalBroadcast()

                # if the request had a source, forward it along
                if npdu.npduSADR:
                    whoisrtn.npduSADR = npdu.npduSADR
                else:
                    whoisrtn.npduSADR = RemoteStation(
                        adapter.adapterNet, npdu.pduSource.addrAddr
                    )
                if _debug:
                    NetworkServiceElement._debug("    - whoisrtn: %r", whoisrtn)

                # send it to all of the (other) adapters
                for xadapter in sap.adapters.values():
                    if xadapter is not adapter:
                        if _debug:
                            NetworkServiceElement._debug(
                                "    - sending on adapter: %r", xadapter
                            )
                        await self.request(xadapter, whoisrtn)

    async def IAmRouterToNetwork(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug("IAmRouterToNetwork %r %r", adapter, npdu)

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)
        if _debug:
            NetworkServiceElement._debug("    - sap: %r", sap)

        # pass along to the service access point
        sap.update_router_references(
            adapter.adapterNet, npdu.pduSource, npdu.iartnNetworkList
        )

        # skip forwarding to other adpaters if this is not a router
        if len(sap.adapters) == 1:
            if _debug:
                NetworkServiceElement._debug("    - not a router")
        else:
            if _debug:
                NetworkServiceElement._debug("    - forwarding to other adapters")

            # build a broadcast annoucement
            iamrtn = IAmRouterToNetwork(
                npdu.iartnNetworkList,
                destination=LocalBroadcast(),
                user_data=npdu.pduUserData,
            )

            # send it to all of the other adapters
            for xadapter in sap.adapters.values():
                if xadapter is not adapter:
                    if _debug:
                        NetworkServiceElement._debug(
                            "    - sending on adapter: %r", xadapter
                        )
                    await self.request(xadapter, iamrtn)

        # look for pending requests for the networks
        for who_is_router_to_network_future in self.who_is_router_to_network_futures:
            who_is_router_to_network_future.match(adapter, npdu)

    async def ICouldBeRouterToNetwork(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug("ICouldBeRouterToNetwork %r %r", adapter, npdu)

    async def RejectMessageToNetwork(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug("RejectMessageToNetwork %r %r", adapter, npdu)

    async def RouterBusyToNetwork(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug("RouterBusyToNetwork %r %r", adapter, npdu)

    async def RouterAvailableToNetwork(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug(
                "RouterAvailableToNetwork %r %r", adapter, npdu
            )

    async def InitializeRoutingTable(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug("InitializeRoutingTable %r %r", adapter, npdu)

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)
        if _debug:
            NetworkServiceElement._debug("    - sap: %r", sap)

        adapter_list = list(sap.adapters.values())
        if len(adapter_list) == 1:
            if _debug:
                NetworkServiceElement._debug("    - not a router")
            return

        if _debug:
            NetworkServiceAccessPoint._debug(
                "    - router_info_cache: %r", sap.router_info_cache
            )
            for k, v in sap.router_info_cache.routers.items():
                NetworkServiceAccessPoint._debug("    - %r: %r", k, v)

        # build a list of routing table entries
        routing_table_entries: List[RoutingTableEntry] = []

        # loop through the adapters
        for i, xadapter in enumerate(adapter_list):
            if _debug:
                NetworkServiceElement._debug("    - xadapter: %r", xadapter)

            # add the direct network
            routing_table_entries.append(
                RoutingTableEntry(xadapter.adapterNet, i + 1, b"")
            )

        if routing_table_entries:
            if _debug:
                NetworkServiceElement._debug(
                    "    - found these: %r", routing_table_entries
                )

            # build a response
            irta = InitializeRoutingTableAck(
                routing_table_entries, user_data=npdu.pduUserData
            )
            irta.pduDestination = npdu.pduSource

            # send it back
            await self.response(adapter, irta)

    async def InitializeRoutingTableAck(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug(
                "InitializeRoutingTableAck %r %r", adapter, npdu
            )

        # look for pending requests
        for initialize_routing_table_future in self.initialize_routing_table_futures:
            initialize_routing_table_future.match(adapter, npdu)

    async def EstablishConnectionToNetwork(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug(
                "EstablishConnectionToNetwork %r %r", adapter, npdu
            )

    async def DisconnectConnectionToNetwork(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug(
                "DisconnectConnectionToNetwork %r %r", adapter, npdu
            )

    async def WhatIsNetworkNumber(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug("WhatIsNetworkNumber %r %r", adapter, npdu)

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)

        # check to see if the local network is known
        if adapter.adapterNet is None:
            if _debug:
                NetworkServiceElement._debug("   - local network not known")
            return

        # if this is not a router, wait for somebody else to answer
        if npdu.pduDestination.addrType == Address.localBroadcastAddr:
            if _debug:
                NetworkServiceElement._debug("    - local broadcast request")

            if len(sap.adapters) == 1:
                if _debug:
                    NetworkServiceElement._debug("    - not a router")

        # send out what we know
        await self.network_number_is(adapter)

    def NetworkNumberIs(self, adapter, npdu):
        if _debug:
            NetworkServiceElement._debug("NetworkNumberIs %r %r", adapter, npdu)

        # reference the service access point
        sap = cast(NetworkServiceAccessPoint, self.elementService)

        # if this was not sent as a broadcast, ignore it
        # if npdu.pduDestination.addrType != Address.localBroadcastAddr:
        #     if _debug:
        #         NetworkServiceElement._debug("    - not broadcast")
        #     return

        # see if someone is waiting for this result
        if adapter in self.what_is_network_number_resolution:
            future = self.what_is_network_number_resolution[adapter]
            future.set_result(npdu.nniNet)

        # check to see if the local network is known
        if adapter.adapterNet is None:
            if _debug:
                NetworkServiceElement._debug(
                    "   - local network not known: %r", list(sap.adapters.keys())
                )

            # update the routing information
            sap.router_info_cache.update_source_network(None, npdu.nniNet)

            # delete the reference from an unknown network
            del sap.adapters[None]

            adapter.adapterNet = npdu.nniNet
            adapter.adapterNetConfigured = NetworkNumberQuality.learned

            # we now know what network this is
            sap.adapters[adapter.adapterNet] = adapter

            if _debug:
                NetworkServiceElement._debug("   - local network learned")
            return

        # check if this matches what we have
        if adapter.adapterNet == npdu.nniNet:
            if _debug:
                NetworkServiceElement._debug("   - matches what we have")
            return

        # check it this matches what we know, if we know it
        if adapter.adapterNetConfigured == NetworkNumberQuality.configured:
            if _debug:
                NetworkServiceElement._debug("   - doesn't match what we know")
            return

        if _debug:
            NetworkServiceElement._debug("   - learning something new")

        # update the routing information
        sap.router_info_cache.update_source_network(adapter.adapterNet, npdu.nniNet)

        # delete the reference from the old (learned) network
        del sap.adapters[adapter.adapterNet]

        adapter.adapterNet = npdu.nniNet
        adapter.adapterNetConfigured = npdu.nniFlag

        # we now know what network this is
        sap.adapters[adapter.adapterNet] = adapter
