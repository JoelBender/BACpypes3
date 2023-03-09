"""
Network Layer Protocol Data Units
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from .errors import DecodingError
from .debugging import ModuleLogger, DebugContents, bacpypes_debugging, btox
from .comm import Client, Server

from .pdu import (
    Address,
    RemoteStation,
    RemoteBroadcast,
    GlobalBroadcast,
    PCI,
    PDUData,
    PDU,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# a dictionary of message type values and classes
npdu_types = {}


def register_npdu_type(class_):
    npdu_types[class_.pduType] = class_
    return class_


#
#  NPCI
#


@bacpypes_debugging
class NPCI(PCI, DebugContents):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "npduVersion",
        "npduControl",
        "npduDADR",
        "npduSADR",
        "npduHopCount",
        "npduNetMessage",
        "npduVendorID",
    )

    whoIsRouterToNetwork = 0x00
    iAmRouterToNetwork = 0x01
    iCouldBeRouterToNetwork = 0x02
    rejectMessageToNetwork = 0x03
    routerBusyToNetwork = 0x04
    routerAvailableToNetwork = 0x05
    initializeRoutingTable = 0x06
    initializeRoutingTableAck = 0x07
    establishConnectionToNetwork = 0x08
    disconnectConnectionToNetwork = 0x09
    challengeRequest = 0x0A
    securityPayload = 0x0B
    securityResponse = 0x0C
    requestKeyUpdate = 0x0D
    updateKeySet = 0x0E
    updateDistributionKey = 0x0F
    requestMasterKey = 0x10
    setMasterKey = 0x11
    whatIsNetworkNumber = 0x12
    networkNumberIs = 0x13

    npduVersion: int = 1
    npduControl = None
    npduDADR: Optional[Address] = None
    npduSADR: Optional[Address] = None
    npduHopCount: int
    npduNetMessage: Optional[int] = None
    npduVendorID: int

    def __init__(self, *args, **kwargs):
        PCI.__init__(self, *args, **kwargs)

    def update(self, npci):
        PCI.update(self, npci)

        # skip over fields that aren't set
        for k in NPCI._debug_contents:
            if hasattr(npci, k):
                setattr(self, k, getattr(npci, k))

    def encode(self) -> PDU:
        """Encode the contents of the NPCI as a PDU."""
        if _debug:
            NPCI._debug("encode")

        # create a PDU and save the PCI contents
        pdu = PDU()
        PCI.update(pdu, self)

        # only version 1 messages supported
        pdu.put(self.npduVersion)

        # build the flags
        if self.npduNetMessage is not None:
            netLayerMessage = 0x80
        else:
            netLayerMessage = 0x00

        # map the destination address
        dnetPresent = 0x00
        if self.npduDADR is not None:
            dnetPresent = 0x20

        # map the source address
        snetPresent = 0x00
        if self.npduSADR is not None:
            snetPresent = 0x08

        # encode the control octet
        control = netLayerMessage | dnetPresent | snetPresent
        if self.pduExpectingReply:
            control |= 0x04
        control |= self.pduNetworkPriority & 0x03
        self.npduControl = control
        pdu.put(control)

        # encode the destination address
        if dnetPresent:
            assert self.npduDADR
            if self.npduDADR.addrType == Address.remoteStationAddr:
                pdu.put_short(self.npduDADR.addrNet)  # type: ignore[arg-type]
                pdu.put(self.npduDADR.addrLen)  # type: ignore[arg-type]
                pdu.put_data(self.npduDADR.addrAddr)  # type: ignore[arg-type]
            elif self.npduDADR.addrType == Address.remoteBroadcastAddr:
                pdu.put_short(self.npduDADR.addrNet)  # type: ignore[arg-type]
                pdu.put(0)
            elif self.npduDADR.addrType == Address.globalBroadcastAddr:
                pdu.put_short(0xFFFF)
                pdu.put(0)

        # encode the source address
        if snetPresent:
            assert self.npduSADR
            pdu.put_short(self.npduSADR.addrNet)  # type: ignore[arg-type]
            pdu.put(self.npduSADR.addrLen)  # type: ignore[arg-type]
            pdu.put_data(self.npduSADR.addrAddr)  # type: ignore[arg-type]

        # put the hop count
        if dnetPresent:
            pdu.put(self.npduHopCount)

        # put the network layer message type (if present)
        if netLayerMessage:
            pdu.put(self.npduNetMessage)  # type: ignore[arg-type]
            # put the vendor ID
            if (self.npduNetMessage >= 0x80) and (self.npduNetMessage <= 0xFF):  # type: ignore[operator]
                pdu.put_short(self.npduVendorID)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPCI:
        """decode the contents of the PDU and return an NPCI."""
        if _debug:
            NPCI._debug("decode %s", str(pdu))

        npci = NPCI()
        PCI.update(npci, pdu)

        # check the length
        if len(pdu.pduData) < 2:
            raise DecodingError("invalid length")

        # only version 1 messages supported
        npci.npduVersion = pdu.get()
        if npci.npduVersion != 0x01:
            raise DecodingError("only version 1 messages supported")

        # decode the control octet
        npci.npduControl = control = pdu.get()
        netLayerMessage = control & 0x80
        dnetPresent = control & 0x20
        snetPresent = control & 0x08
        npci.pduExpectingReply = (control & 0x04) != 0
        npci.pduNetworkPriority = control & 0x03

        # extract the destination address
        if dnetPresent:
            dnet = pdu.get_short()
            dlen = pdu.get()
            dadr = pdu.get_data(dlen)

            if dnet == 0xFFFF:
                npci.npduDADR = GlobalBroadcast()
            elif dlen == 0:
                npci.npduDADR = RemoteBroadcast(dnet)
            else:
                npci.npduDADR = RemoteStation(dnet, dadr)

        # extract the source address
        if snetPresent:
            snet = pdu.get_short()
            slen = pdu.get()
            sadr = pdu.get_data(slen)

            if snet == 0xFFFF:
                raise DecodingError("SADR can't be a global broadcast")
            elif slen == 0:
                raise DecodingError("SADR can't be a remote broadcast")

            npci.npduSADR = RemoteStation(snet, sadr)

        # extract the hop count
        if dnetPresent:
            npci.npduHopCount = pdu.get()

        # extract the network layer message type (if present)
        if netLayerMessage:
            npci.npduNetMessage = pdu.get()
            if (npci.npduNetMessage >= 0x80) and (npci.npduNetMessage <= 0xFF):
                # extract the vendor ID
                npci.npduVendorID = pdu.get_short()
        else:
            # application layer message
            npci.npduNetMessage = None

        return npci

    def npci_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug:
            NPCI._debug("npci_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            if _debug:
                NPCI._debug("    - new use_dict")
            use_dict = as_class()

        # version and control are simple
        use_dict.__setitem__("version", self.npduVersion)
        use_dict.__setitem__("control", self.npduControl)

        # dnet/dlen/dadr
        if self.npduDADR is not None:
            if self.npduDADR.addrType == Address.remoteStationAddr:
                use_dict.__setitem__("dnet", self.npduDADR.addrNet)
                use_dict.__setitem__("dlen", self.npduDADR.addrLen)
                use_dict.__setitem__("dadr", btox(self.npduDADR.addrAddr or b""))
            elif self.npduDADR.addrType == Address.remoteBroadcastAddr:
                use_dict.__setitem__("dnet", self.npduDADR.addrNet)
                use_dict.__setitem__("dlen", 0)
                use_dict.__setitem__("dadr", "")
            elif self.npduDADR.addrType == Address.globalBroadcastAddr:
                use_dict.__setitem__("dnet", 0xFFFF)
                use_dict.__setitem__("dlen", 0)
                use_dict.__setitem__("dadr", "")

        # snet/slen/sadr
        if self.npduSADR is not None:
            use_dict.__setitem__("snet", self.npduSADR.addrNet)
            use_dict.__setitem__("slen", self.npduSADR.addrLen)
            use_dict.__setitem__("sadr", btox(self.npduSADR.addrAddr or b""))

        # hop count
        if self.npduHopCount is not None:
            use_dict.__setitem__("hop_count", self.npduHopCount)

        # network layer message name decoded
        if self.npduNetMessage is not None:
            use_dict.__setitem__("net_message", self.npduNetMessage)
        if self.npduVendorID is not None:
            use_dict.__setitem__("vendor_id", self.npduVendorID)

        # return what we built/updated
        return use_dict


#
#   NPDU
#


@bacpypes_debugging
class NPDU(NPCI, PDUData):
    """
    Network Layer Protocol Data Unit
    """

    _debug: Callable[..., None]

    def __init__(self, *args, **kwargs):
        if _debug:
            NPDU._debug("__init__ %r %r", args, kwargs)
        NPCI.__init__(self, **kwargs)
        PDUData.__init__(self, *args)

    def encode(self) -> PDU:
        if _debug:
            NPDU._debug("encode")

        pdu = NPCI.encode(self)
        PCI.update(pdu, self)
        pdu.put_data(self.pduData)
        if _debug:
            NPDU._debug("    - pdu: %r", pdu)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        if _debug:
            NPDU._debug("decode %r %r", class_, pdu)

        # decode the header
        npci = NPCI.decode(pdu)
        if _debug:
            NPDU._debug("    - npci: %r", npci)

        # build an NPDU, update the header
        npdu = NPDU()
        NPCI.update(npdu, npci)
        npdu.put_data(pdu.pduData)
        if _debug:
            NPDU._debug("    - npdu: %r", npdu)

        return npdu

    def npdu_contents(self, use_dict=None, as_class=dict):
        return PDUData.pdudata_contents(self, use_dict=use_dict, as_class=as_class)

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug:
            NPDU._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the parent classes
        self.npci_contents(use_dict=use_dict, as_class=as_class)
        self.npdu_contents(use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict


#
#   NetworkCodec
#


@bacpypes_debugging
class NetworkCodec(Client[PDU], Server[NPDU]):

    _debug: Callable[..., None]

    def __init__(self, cid=None, sid=None):
        if _debug:
            NetworkCodec._debug("__init__ cid=%r sid=%r", cid, sid)
        Client.__init__(self, cid)
        Server.__init__(self, sid)

    async def indication(self, npdu: NPDU) -> None:
        if _debug:
            NetworkCodec._debug("indication %r", npdu)

        # encode it as a PDU
        pdu = npdu.encode()
        if _debug:
            NetworkCodec._debug("    - pdu: %r", pdu)

        # send it downstream
        await self.request(pdu)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            NetworkCodec._debug("confirmation %r", pdu)

        # decode as an NPDU
        npdu = NPDU.decode(pdu)

        # if this is a network layer message, find the subclass and let it
        # decode the message
        if npdu.npduNetMessage:
            try:
                npdu_class = npdu_types[npdu.npduNetMessage]
            except KeyError:
                raise RuntimeError(f"unrecognized NPDU type: {npdu.npduNetMessage}")
            if _debug:
                NetworkCodec._debug("    - npdu_class: %r", npdu_class)

            # ask the class to decode the rest of the PDU
            npdu = npdu_class.decode(npdu)
        if _debug:
            NetworkCodec._debug("    - npdu: %r", npdu)

        # send it upstream
        await self.response(npdu)


#
#   key_value_contents
#


@bacpypes_debugging
def key_value_contents(use_dict=None, as_class=dict, key_values=()):
    """Return the contents of an object as a dict."""
    if _debug:
        key_value_contents._debug(
            "key_value_contents use_dict=%r as_class=%r key_values=%r",
            use_dict,
            as_class,
            key_values,
        )

    # make/extend the dictionary of content
    if use_dict is None:
        use_dict = as_class()

    # loop through the values and save them
    for k, v in key_values:
        if v is not None:
            if hasattr(v, "dict_contents"):
                v = v.dict_contents(as_class=as_class)
            use_dict.__setitem__(k, v)

    # return what we built/updated
    return use_dict


#
#   WhoIsRouterToNetwork
#


@register_npdu_type
class WhoIsRouterToNetwork(NPDU):

    _debug_contents: Tuple[str, ...] = ("wirtnNetwork",)

    pduType = 0x00
    wirtnNetwork: Optional[int]

    def __init__(self, net: Optional[int] = None, *args, **kwargs):
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = WhoIsRouterToNetwork.pduType
        self.wirtnNetwork = net

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        if self.wirtnNetwork is not None:
            pdu.put_short(self.wirtnNetwork)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        npdu = WhoIsRouterToNetwork()
        if pdu.pduData:
            npdu.wirtnNetwork = pdu.get_short()
        else:
            npdu.wirtnNetwork = None
        return npdu

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "WhoIsRouterToNetwork"),
                ("network", self.wirtnNetwork),
            ),
        )


#
#   IAmRouterToNetwork
#


@register_npdu_type
class IAmRouterToNetwork(NPDU):

    _debug_contents: Tuple[str, ...] = ("iartnNetworkList",)

    pduType = 0x01
    iartnNetworkList: List[int]

    def __init__(self, network_list: List[int] = [], *args, **kwargs):
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = IAmRouterToNetwork.pduType
        self.iartnNetworkList = network_list

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        for net in self.iartnNetworkList:
            pdu.put_short(net)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        network_list = []
        while pdu.pduData:
            network_list.append(pdu.get_short())
        return IAmRouterToNetwork(network_list)

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "IAmRouterToNetwork"),
                ("network_list", self.iartnNetworkList),
            ),
        )


#
#   ICouldBeRouterToNetwork
#


@register_npdu_type
class ICouldBeRouterToNetwork(NPDU):

    _debug_contents: Tuple[str, ...] = ("icbrtnNetwork", "icbrtnPerformanceIndex")

    pduType = 0x02
    icbrtnNetwork: int
    icbrtnPerformanceIndex: int

    def __init__(self, network: int, performance_index: int, *args, **kwargs):
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = ICouldBeRouterToNetwork.pduType
        self.icbrtnNetwork = network
        self.icbrtnPerformanceIndex = performance_index

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        pdu.put_short(self.icbrtnNetwork)
        pdu.put(self.icbrtnPerformanceIndex)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        network = pdu.get_short()
        performance_index = pdu.get()
        return ICouldBeRouterToNetwork(network, performance_index)

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "ICouldBeRouterToNetwork"),
                ("network", self.icbrtnNetwork),
                ("performance_index", self.icbrtnPerformanceIndex),
            ),
        )


#
#   RejectMessageToNetwork
#


@register_npdu_type
class RejectMessageToNetwork(NPDU):

    _debug_contents: Tuple[str, ...] = ("rmtnRejectReason", "rmtnDNET")

    pduType = 0x03
    rmtnRejectionReason: int
    rmtnDNET: int

    def __init__(self, reason: int, dnet: int, *args, **kwargs):
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = RejectMessageToNetwork.pduType
        self.rmtnRejectionReason = reason
        self.rmtnDNET = dnet

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        pdu.put(self.rmtnRejectionReason)
        pdu.put_short(self.rmtnDNET)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        reason = pdu.get()
        dnet = pdu.get_short()
        return RejectMessageToNetwork(reason, dnet)

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "RejectMessageToNetwork"),
                ("reject_reason", self.rmtnRejectionReason),
                ("dnet", self.rmtnDNET),
            ),
        )


#
#   RouterBusyToNetwork
#


@register_npdu_type
class RouterBusyToNetwork(NPDU):

    _debug_contents: Tuple[str, ...] = ("rbtnNetworkList",)

    pduType = 0x04
    rbtnNetworkList: List[int]

    def __init__(self, network_list: List[int], *args, **kwargs):
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = RouterBusyToNetwork.pduType
        self.rbtnNetworkList = network_list

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        for net in self.rbtnNetworkList:
            pdu.put_short(net)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        network_list = []
        while pdu.pduData:
            network_list.append(pdu.get_short())
        return RouterBusyToNetwork(network_list)

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "RouterBusyToNetwork"),
                ("network_list", self.rbtnNetworkList),
            ),
        )


#
#   RouterAvailableToNetwork
#


@register_npdu_type
class RouterAvailableToNetwork(NPDU):

    _debug_contents: Tuple[str, ...] = ("ratnNetworkList",)

    pduType = 0x05
    ratnNetworkList: List[int]

    def __init__(self, network_list: List[int], *args, **kwargs):
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = RouterAvailableToNetwork.pduType
        self.ratnNetworkList = network_list

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        for net in self.ratnNetworkList:
            pdu.put_short(net)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        network_list = []
        while pdu.pduData:
            network_list.append(pdu.get_short())
        return RouterAvailableToNetwork(network_list)

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "RouterAvailableToNetwork"),
                ("network_list", self.ratnNetworkList),
            ),
        )


#
#   Routing Table Entry
#


class RoutingTableEntry(DebugContents):

    _debug_contents: Tuple[str, ...] = ("rtDNET", "rtPortID", "rtPortInfo")
    rtDNET: int
    rtPortID: int
    rtPortInfo: bytes

    def __init__(self, dnet: int, port_id: int, port_info: bytes) -> None:
        self.rtDNET = dnet
        self.rtPortID = port_id
        self.rtPortInfo = port_info

    def __eq__(self, other):
        """Return true iff entries are identical."""
        return (
            (self.rtDNET == other.rtDNET)
            and (self.rtPortID == other.rtPortID)
            and (self.rtPortInfo == other.rtPortInfo)
        )

    def dict_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # save the content
        use_dict.__setitem__("dnet", self.rtDNET)
        use_dict.__setitem__("port_id", self.rtPortID)
        use_dict.__setitem__("port_info", self.rtPortInfo)

        # return what we built/updated
        return use_dict


#
#   InitializeRoutingTable
#


@register_npdu_type
class InitializeRoutingTable(NPDU):
    pduType = 0x06
    _debug_contents: Tuple[str, ...] = ("irtTable++",)

    irtTable: List[RoutingTableEntry]

    def __init__(self, routing_table: List[RoutingTableEntry], *args, **kwargs):
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = InitializeRoutingTable.pduType
        self.irtTable = routing_table

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        pdu.put(len(self.irtTable))
        for rte in self.irtTable:
            pdu.put_short(rte.rtDNET)
            pdu.put(rte.rtPortID)
            pdu.put(len(rte.rtPortInfo))
            pdu.put_data(rte.rtPortInfo)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        routing_table = []

        rtLength = pdu.get()
        for i in range(rtLength):
            dnet = pdu.get_short()
            port_id = pdu.get()
            port_info_len = pdu.get()
            port_info = pdu.get_data(port_info_len)
            rte = RoutingTableEntry(dnet, port_id, port_info)
            routing_table.append(rte)

        return InitializeRoutingTable(routing_table)

    def npdu_contents(self, use_dict=None, as_class=dict):
        routing_table = []
        for rte in self.irtTable:
            routing_table.append(rte.dict_contents(as_class=as_class))

        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "InitializeRoutingTable"),
                ("routing_table", routing_table),
            ),
        )


#
#   InitializeRoutingTableAck
#


@register_npdu_type
class InitializeRoutingTableAck(NPDU):
    pduType = 0x07
    _debug_contents: Tuple[str, ...] = ("irtaTable++",)
    irtaTable: List[RoutingTableEntry]

    def __init__(self, routing_table: List[RoutingTableEntry], *args, **kwargs) -> None:
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = InitializeRoutingTableAck.pduType
        self.irtaTable = routing_table

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        pdu.put(len(self.irtaTable))
        for rte in self.irtaTable:
            pdu.put_short(rte.rtDNET)
            pdu.put(rte.rtPortID)
            pdu.put(len(rte.rtPortInfo))
            pdu.put_data(rte.rtPortInfo)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        routing_table = []

        rtLength = pdu.get()
        for i in range(rtLength):
            dnet = pdu.get_short()
            port_id = pdu.get()
            port_info_len = pdu.get()
            port_info = pdu.get_data(port_info_len)
            rte = RoutingTableEntry(dnet, port_id, port_info)
            routing_table.append(rte)
        return InitializeRoutingTableAck(routing_table)

    def npdu_contents(self, use_dict=None, as_class=dict):
        routing_table = []
        for rte in self.irtaTable:
            routing_table.append(rte.dict_contents(as_class=as_class))

        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "InitializeRoutingTableAck"),
                ("routing_table", routing_table),
            ),
        )


#
#   EstablishConnectionToNetwork
#


@register_npdu_type
class EstablishConnectionToNetwork(NPDU):

    _debug_contents: Tuple[str, ...] = ("ectnDNET", "ectnTerminationTime")

    pduType = 0x08
    ectnDNET: int
    ectnTerminationTime: int

    def __init__(self, dnet: int, termination_time: int, *args, **kwargs):
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = EstablishConnectionToNetwork.pduType
        self.ectnDNET = dnet
        self.ectnTerminationTime = termination_time

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        pdu.put_short(self.ectnDNET)
        pdu.put(self.ectnTerminationTime)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        dnet = pdu.get_short()
        termination_time = pdu.get()
        return EstablishConnectionToNetwork(dnet, termination_time)

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "EstablishConnectionToNetwork"),
                ("dnet", self.ectnDNET),
                ("termination_time", self.ectnTerminationTime),
            ),
        )


#
#   DisconnectConnectionToNetwork
#


@register_npdu_type
class DisconnectConnectionToNetwork(NPDU):

    _debug_contents: Tuple[str, ...] = ("dctnDNET",)

    pduType = 0x09
    dctnDNET: int

    def __init__(self, dnet: int, *args, **kwargs) -> None:
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = DisconnectConnectionToNetwork.pduType
        self.dctnDNET = dnet

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        pdu.put_short(self.dctnDNET)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        dnet = pdu.get_short()
        return DisconnectConnectionToNetwork(dnet)

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "DisconnectConnectionToNetwork"),
                ("dnet", self.dctnDNET),
            ),
        )


#
#   WhatIsNetworkNumber
#


@register_npdu_type
class WhatIsNetworkNumber(NPDU):

    _debug_contents: Tuple[str, ...] = ()

    pduType = 0x12

    def __init__(self, *args, **kwargs) -> None:
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = WhatIsNetworkNumber.pduType

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        return WhatIsNetworkNumber()

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "WhatIsNetworkNumber"),),
        )


#
#   NetworkNumberIs
#


@register_npdu_type
class NetworkNumberIs(NPDU):

    _debug_contents: Tuple[str, ...] = (
        "nniNet",
        "nniFlag",
    )

    pduType = 0x13
    nniNet: int
    nniFlag: int

    def __init__(self, net: int, flag: int, *args, **kwargs):
        NPDU.__init__(self, *args, **kwargs)

        self.npduNetMessage = NetworkNumberIs.pduType
        self.nniNet = net
        self.nniFlag = flag

    def encode(self) -> PDU:
        pdu = NPCI.encode(self)
        pdu.put_short(self.nniNet)
        pdu.put(self.nniFlag)
        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> NPDU:
        net = pdu.get_short()
        flag = pdu.get()
        return NetworkNumberIs(net, flag)

    def npdu_contents(self, use_dict=None, as_class=dict):
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "NetworkNumberIs"),
                ("net", self.nniNet),
                ("flag", self.nniFlag),
            ),
        )
