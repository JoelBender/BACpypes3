"""
BACnet IPv4 Virtual Link Layer Protocol Data Units
"""

from __future__ import annotations

import socket
from typing import Callable, Optional, Tuple

from ..errors import DecodingError
from ..debugging import ModuleLogger, DebugContents, bacpypes_debugging

from ..pdu import IPv4Address, PCI, PDUData, PDU
from ..comm import Client, Server

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# a dictionary of message type values and classes
pdu_types = {}


def register_bvlpdu_type(class_):
    pdu_types[class_.pduType] = class_
    return class_


#
#   LPCI
#


@bacpypes_debugging
class LPCI(PCI, DebugContents):
    """
    Link Layer Protocol Control Information
    """

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = ("bvlciType", "bvlciFunction", "bvlciLength")

    result = 0x00
    writeBroadcastDistributionTable = 0x01
    readBroadcastDistributionTable = 0x02
    readBroadcastDistributionTableAck = 0x03
    forwardedNPDU = 0x04
    registerForeignDevice = 0x05
    readForeignDeviceTable = 0x06
    readForeignDeviceTableAck = 0x07
    deleteForeignDeviceTableEntry = 0x08
    distributeBroadcastToNetwork = 0x09
    originalUnicastNPDU = 0x0A
    originalBroadcastNPDU = 0x0B

    bvlciType: int = 0x81
    bvlciFunction: int
    bvlciLength: int

    def __init__(self, *args, **kwargs) -> None:
        if _debug:
            LPCI._debug("__init__ %r %r", args, kwargs)
        PCI.__init__(self, *args, **kwargs)

    def update(self, bvlci: LPCI) -> None:  # type: ignore[override]
        if _debug:
            LPCI._debug("update %r", bvlci)

        PCI.update(self, bvlci)

        # skip over fields that aren't set
        for k in LPCI._debug_contents:
            if hasattr(bvlci, k):
                setattr(self, k, getattr(bvlci, k))

    def encode(self) -> PDU:
        """Encode the contents of the LPCI as a PDU."""
        if _debug:
            LPCI._debug("encode")

        # create a PDU and save the PCI contents
        pdu = PDU()
        PCI.update(pdu, self)

        pdu.put(self.bvlciType)
        pdu.put(self.bvlciFunction)
        pdu.put_short(self.bvlciLength)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPCI:
        """Decode the contents of the PDU and return a LPCI."""
        if _debug:
            LPCI._debug("decode %r", pdu)

        lpci = LPCI()
        PCI.update(lpci, pdu)

        lpci.bvlciType = pdu.get()
        if lpci.bvlciType != 0x81:
            raise DecodingError("invalid LPCI type")

        lpci.bvlciFunction = pdu.get()
        lpci.bvlciLength = pdu.get_short()

        if lpci.bvlciLength != len(pdu.pduData) + 4:
            raise DecodingError("invalid LPCI length")

        return lpci

    def lpci_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        if _debug:
            LPCI._debug("lpci_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # skip over fields that aren't set
        for k in LPCI._debug_contents:
            if hasattr(self, k):
                use_dict.__setitem__(k, getattr(self, k))

        # return what we built/updated
        return use_dict


#
#   LPDU
#


@bacpypes_debugging
class LPDU(LPCI, PDUData):
    """
    Link Layer Protocol Data Unit
    """

    _debug: Callable[..., None]

    def __init__(self, *args, **kwargs) -> None:
        if _debug:
            LPDU._debug("__init__ %r %r", args, kwargs)
        LPCI.__init__(self, **kwargs)
        PDUData.__init__(self, *args)

    def encode(self) -> PDU:
        if _debug:
            LPDU._debug("encode")

        # encode the header
        pdu = LPCI.encode(self)
        PCI.update(pdu, self)
        pdu.put_data(self.pduData)
        if _debug:
            LPDU._debug("    - pdu: %r", pdu)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:
        if _debug:
            LPDU._debug("decode %r %r", class_, pdu)

        # decode the header
        lpci = LPCI.decode(pdu)
        if _debug:
            LPDU._debug("    - lpci: %r", lpci)

        # build an LPDU, update the header
        lpdu = LPDU()
        LPCI.update(lpdu, lpci)
        lpdu.put_data(pdu.pduData)
        if _debug:
            LPDU._debug("    - lpdu: %r", lpdu)

        return lpdu

    def lpdu_contents(self, use_dict=None, as_class=dict) -> dict:
        return PDUData.pdudata_contents(self, use_dict=use_dict, as_class=as_class)

    def dict_contents(self, use_dict=None, as_class=dict) -> dict:
        """Return the contents of an object as a dict."""
        if _debug:
            LPDU._debug("dict_contents use_dict=%r as_class=%r", use_dict, as_class)

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the parent classes
        self.lpci_contents(use_dict=use_dict, as_class=as_class)
        self.lpdu_contents(use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict

    debug_contents = DebugContents.debug_contents  # type: ignore[assignment]


#
#   BVLLCodec
#


@bacpypes_debugging
class BVLLCodec(Client[PDU], Server[LPDU]):
    _debug: Callable[..., None]

    def __init__(self, cid=None, sid=None) -> None:
        if _debug:
            BVLLCodec._debug("__init__ cid=%r sid=%r", cid, sid)
        Client.__init__(self, cid)
        Server.__init__(self, sid)

    async def indication(self, lpdu: LPDU) -> None:
        if _debug:
            BVLLCodec._debug("indication %r", lpdu)

        # encode it as a PDU
        pdu = lpdu.encode()
        if _debug:
            BVLLCodec._debug("    - pdu: %r", pdu)

        # send it downstream
        await self.request(pdu)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            BVLLCodec._debug("confirmation %r", pdu)

        # decode the header
        lpci = LPCI.decode(pdu)

        # find the appropriate LPDU subclass
        try:
            lpdu_class = pdu_types[lpci.bvlciFunction]
        except KeyError:
            raise DecodingError(f"unrecognized BVLL function: {lpci.bvlciFunction}")
        if _debug:
            BVLLCodec._debug("    - lpdu_class: %r", lpdu_class)

        # ask the subclass to decode the rest of the pdu
        lpdu = lpdu_class.decode(pdu)
        LPCI.update(lpdu, lpci)
        if _debug:
            BVLLCodec._debug("    - lpdu: %r", lpdu)

        # send it upstream
        await self.response(lpdu)


#
#   key_value_contents
#


@bacpypes_debugging
def key_value_contents(use_dict=None, as_class=dict, key_values=()):
    """
    Update the contents of a dictionary with the keys and values that
    are not None, and if the value as a dict_contents() function then
    call it for nested details.
    """
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
#   Foreign Device Table Entry
#


class FDTEntry(DebugContents):
    _debug_contents = ("fdAddress", "fdTTL", "fdRemain")

    fdAddress: IPv4Address
    fdTTL: int
    fdRemain: int

    def __init__(self):
        self.fdAddress = None
        self.fdTTL = None
        self.fdRemain = None

    def __eq__(self, other):
        """Return true iff entries are identical."""
        return (
            (self.fdAddress == other.fdAddress)
            and (self.fdTTL == other.fdTTL)
            and (self.fdRemain == other.fdRemain)
        )

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # save the content
        use_dict.__setitem__("address", str(self.fdAddress))
        use_dict.__setitem__("ttl", self.fdTTL)
        use_dict.__setitem__("remaining", self.fdRemain)

        # return what we built/updated
        return use_dict


#
#   Result
#


@register_bvlpdu_type
class Result(LPDU, BaseException):
    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = ("bvlciResultCode",)

    pduType = LPCI.result

    def __init__(self, code: Optional[int] = None, *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.result
        self.bvlciLength = 6
        self.bvlciResultCode = code

    def encode(self) -> PDU:
        if _debug:
            Result._debug("encode")
        assert isinstance(self.bvlciResultCode, int)

        pdu = LPCI.encode(self)
        pdu.put_short(self.bvlciResultCode)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            Result._debug("decode %r", pdu)

        lpdu = Result()
        lpdu.bvlciResultCode = pdu.get_short()
        return lpdu

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("result_code", self.bvlciResultCode),),
        )


#
#   WriteBroadcastDistributionTable
#


def _count_set_bits(n: int) -> int:
    count: int = 0
    while n:
        n &= n - 1
        count += 1
    return count


@register_bvlpdu_type
class WriteBroadcastDistributionTable(LPDU):
    _debug: Callable[..., None]
    _debug_contents = ("bvlciBDT",)

    pduType = LPCI.writeBroadcastDistributionTable

    def __init__(self, bdt=[], *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.writeBroadcastDistributionTable
        self.bvlciLength = 4 + 10 * len(bdt)
        self.bvlciBDT = bdt

    def encode(self) -> PDU:
        if _debug:
            WriteBroadcastDistributionTable._debug("encode")

        # make sure the length is correct
        self.bvlciLength = 4 + 10 * len(self.bvlciBDT)

        pdu = LPCI.encode(self)
        for bdte in self.bvlciBDT:
            pdu.put_data(bdte.addrAddr)
            pdu.put_data(bdte.netmask.packed)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            WriteBroadcastDistributionTable._debug("decode %r", pdu)

        lpdu = WriteBroadcastDistributionTable()
        lpdu.bvlciBDT = []
        while pdu.pduData:
            addr = socket.inet_ntoa(pdu.get_data(4))
            port = pdu.get_short()
            mask = _count_set_bits(pdu.get_long())
            bdte = IPv4Address(f"{addr}/{mask}:{port}")
            lpdu.bvlciBDT.append(bdte)

        return lpdu

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        broadcast_distribution_table = []
        for bdte in self.bvlciBDT:
            broadcast_distribution_table.append(str(bdte))

        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "WriteBroadcastDistributionTable"),
                ("bdt", broadcast_distribution_table),
            ),
        )


#
#   ReadBroadcastDistributionTable
#


@register_bvlpdu_type
class ReadBroadcastDistributionTable(LPDU):
    pduType = LPCI.readBroadcastDistributionTable

    def __init__(self, *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.readBroadcastDistributionTable
        self.bvlciLength = 4

    def encode(self) -> PDU:
        return LPCI.encode(self)

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        return ReadBroadcastDistributionTable()

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "ReadBroadcastDistributionTable"),),
        )


#
#   ReadBroadcastDistributionTableAck
#


@register_bvlpdu_type
class ReadBroadcastDistributionTableAck(LPDU):
    _debug: Callable[..., None]
    _debug_contents = ("bvlciBDT",)

    pduType = LPCI.readBroadcastDistributionTableAck

    def __init__(self, bdt=[], *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.readBroadcastDistributionTableAck
        self.bvlciLength = 4 + 10 * len(bdt)
        self.bvlciBDT = bdt

    def encode(self) -> PDU:
        if _debug:
            ReadBroadcastDistributionTableAck._debug("encode")

        # make sure the length is correct
        self.bvlciLength = 4 + 10 * len(self.bvlciBDT)

        pdu = LPCI.encode(self)
        for bdte in self.bvlciBDT:
            pdu.put_data(bdte.addrAddr)
            pdu.put_data(bdte.netmask.packed)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            ReadBroadcastDistributionTableAck._debug("decode %r", pdu)

        lpdu = ReadBroadcastDistributionTableAck()
        lpdu.bvlciBDT = []
        while pdu.pduData:
            addr = socket.inet_ntoa(pdu.get_data(4))
            port = pdu.get_short()
            mask = _count_set_bits(pdu.get_long())
            bdte = IPv4Address(f"{addr}/{mask}:{port}")
            lpdu.bvlciBDT.append(bdte)

        return lpdu

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        broadcast_distribution_table = []
        for bdte in self.bvlciBDT:
            broadcast_distribution_table.append(str(bdte))

        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "ReadBroadcastDistributionTableAck"),
                ("bdt", broadcast_distribution_table),
            ),
        )


#
#   ForwardedNPDU
#


@register_bvlpdu_type
class ForwardedNPDU(LPDU):
    _debug: Callable[..., None]
    _debug_contents = ("bvlciAddress",)

    pduType = LPCI.forwardedNPDU

    def __init__(self, addr=None, *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.forwardedNPDU
        self.bvlciLength = 10 + len(self.pduData)
        self.bvlciAddress = addr

    def encode(self) -> PDU:
        if _debug:
            ForwardedNPDU._debug("encode")

        # make sure the length is correct
        self.bvlciLength = 10 + len(self.pduData)

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciAddress.addrAddr)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            ForwardedNPDU._debug("decode %r", pdu)

        addr = IPv4Address(pdu.get_data(6))
        data = pdu.get_data(len(pdu.pduData))

        return ForwardedNPDU(addr, data)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "ForwardedNPDU"),
                ("address", str(self.bvlciAddress)),
            ),
        )

        # this message has data
        PDUData.dict_contents(self, use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict


#
#   RegisterForeignDevice
#


@register_bvlpdu_type
class RegisterForeignDevice(LPDU):
    _debug: Callable[..., None]
    _debug_contents = ("bvlciTimeToLive",)

    pduType = LPCI.registerForeignDevice

    def __init__(self, ttl=None, *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.registerForeignDevice
        self.bvlciLength = 6
        self.bvlciTimeToLive = ttl

    def encode(self) -> PDU:
        if _debug:
            RegisterForeignDevice._debug("encode")

        pdu = LPCI.encode(self)
        pdu.put_short(self.bvlciTimeToLive)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            RegisterForeignDevice._debug("decode %r", pdu)

        ttl = pdu.get_short()

        return RegisterForeignDevice(ttl)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "RegisterForeignDevice"),
                ("ttl", self.bvlciTimeToLive),
            ),
        )


#
#   ReadForeignDeviceTable
#


@register_bvlpdu_type
class ReadForeignDeviceTable(LPDU):
    pduType = LPCI.readForeignDeviceTable

    def __init__(self, *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.readForeignDeviceTable
        self.bvlciLength = 4

    def encode(self) -> PDU:
        return LPCI.encode(self)

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        return ReadForeignDeviceTable()

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "ReadForeignDeviceTable"),),
        )


#
#   ReadForeignDeviceTableAck
#


@register_bvlpdu_type
class ReadForeignDeviceTableAck(LPDU):
    _debug: Callable[..., None]
    _debug_contents = ("bvlciFDT",)

    pduType = LPCI.readForeignDeviceTableAck

    def __init__(self, fdt=[], *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.readForeignDeviceTableAck
        self.bvlciLength = 4 + 10 * len(fdt)
        self.bvlciFDT = fdt

    def encode(self) -> PDU:
        if _debug:
            ReadForeignDeviceTableAck._debug("encode")

        # make sure the length is correct
        self.bvlciLength = 4 + 10 * len(self.bvlciFDT)

        pdu = LPCI.encode(self)
        for fdte in self.bvlciFDT:
            pdu.put_data(fdte.fdAddress.addrAddr)
            pdu.put_short(fdte.fdTTL)
            pdu.put_short(fdte.fdRemain)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            ReadForeignDeviceTableAck._debug("decode %r", pdu)

        lpdu = ReadForeignDeviceTableAck()
        lpdu.bvlciFDT = []
        while pdu.pduData:
            fdte = FDTEntry()
            fdte.fdAddress = IPv4Address(pdu.get_data(6))
            fdte.fdTTL = pdu.get_short()
            fdte.fdRemain = pdu.get_short()
            lpdu.bvlciFDT.append(fdte)

        return lpdu

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        foreign_device_table = []
        for fdte in self.bvlciFDT:
            foreign_device_table.append(fdte.lpdu_contents(as_class=as_class))

        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "ReadForeignDeviceTableAck"),
                ("foreign_device_table", foreign_device_table),
            ),
        )


#
#   DeleteForeignDeviceTableEntry
#


@register_bvlpdu_type
class DeleteForeignDeviceTableEntry(LPDU):
    _debug: Callable[..., None]
    _debug_contents = ("bvlciAddress",)

    pduType = LPCI.deleteForeignDeviceTableEntry

    def __init__(self, addr=None, *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.deleteForeignDeviceTableEntry
        self.bvlciLength = 10
        self.bvlciAddress = addr

    def encode(self) -> PDU:
        if _debug:
            DeleteForeignDeviceTableEntry._debug("encode")

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciAddress.addrAddr)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            DeleteForeignDeviceTableEntry._debug("decode %r", pdu)

        addr = IPv4Address(pdu.get_data(6))

        return DeleteForeignDeviceTableEntry(addr)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("function", "DeleteForeignDeviceTableEntry"),
                ("address", str(self.bvlciAddress)),
            ),
        )


#
#   DistributeBroadcastToNetwork
#


@register_bvlpdu_type
class DistributeBroadcastToNetwork(LPDU):
    _debug: Callable[..., None]

    pduType = LPCI.distributeBroadcastToNetwork

    def __init__(self, *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.distributeBroadcastToNetwork
        self.bvlciLength = 4 + len(self.pduData)

    def encode(self) -> PDU:
        if _debug:
            DistributeBroadcastToNetwork._debug("encode")

        self.bvlciLength = 4 + len(self.pduData)

        pdu = LPCI.encode(self)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            DistributeBroadcastToNetwork._debug("decode %r", pdu)

        data = pdu.get_data(len(pdu.pduData))

        return DistributeBroadcastToNetwork(data)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "DistributeBroadcastToNetwork"),),
        )

        # this message has data
        PDUData.dict_contents(self, use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict


#
#   OriginalUnicastNPDU
#


@register_bvlpdu_type
class OriginalUnicastNPDU(LPDU):
    _debug: Callable[..., None]

    pduType = LPCI.originalUnicastNPDU

    def __init__(self, *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.originalUnicastNPDU
        self.bvlciLength = 4 + len(self.pduData)

    def encode(self) -> PDU:
        if _debug:
            OriginalUnicastNPDU._debug("encode")

        self.bvlciLength = 4 + len(self.pduData)

        pdu = LPCI.encode(self)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            OriginalUnicastNPDU._debug("decode %r", pdu)

        data = pdu.get_data(len(pdu.pduData))

        return OriginalUnicastNPDU(data)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "OriginalUnicastNPDU"),),
        )

        # this message has data
        PDUData.dict_contents(self, use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict


#
#   OriginalBroadcastNPDU
#


@register_bvlpdu_type
class OriginalBroadcastNPDU(LPDU):
    _debug: Callable[..., None]

    pduType = LPCI.originalBroadcastNPDU

    def __init__(self, *args, **kwargs):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciFunction = LPCI.originalBroadcastNPDU
        self.bvlciLength = 4 + len(self.pduData)

    def encode(self) -> PDU:
        if _debug:
            OriginalBroadcastNPDU._debug("encode")

        self.bvlciLength = 4 + len(self.pduData)

        pdu = LPCI.encode(self)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            OriginalBroadcastNPDU._debug("decode %r", pdu)

        data = pdu.get_data(len(pdu.pduData))

        return OriginalBroadcastNPDU(data)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "OriginalBroadcastNPDU"),),
        )

        # this message has data
        PDUData.dict_contents(self, use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict
