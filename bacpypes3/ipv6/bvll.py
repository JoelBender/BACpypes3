"""
BACnet IPv6 Virtual Link Layer Protocol Data Units
"""

from __future__ import annotations

from typing import Callable, Tuple

from ..errors import DecodingError
from ..debugging import ModuleLogger, DebugContents, bacpypes_debugging

from ..pdu import IPv6Address, VirtualAddress, PCI, PDUData, PDU
from ..comm import Client, Server

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# a dictionary of functions and LPDU classes
pdu_types = {}


def register_bvlpdu_type(class_):
    pdu_types[class_.bvlciFunction] = class_
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
    originalUnicastNPDU = 0x01
    originalBroadcastNPDU = 0x02
    addressResolution = 0x03
    forwardedAddressResolution = 0x04
    addressResolutionACK = 0x05
    virtualAddressResolution = 0x06
    virtualAddressResolutionACK = 0x07
    forwardedNPDU = 0x08
    registerForeignDevice = 0x09
    deleteForeignDeviceTableEntry = 0x0A
    distributeBroadcastToNetwork = 0x0C

    bvlciType: int = 0x82
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
        """Encode the contents of the LPCI into a PDU."""
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
        if lpci.bvlciType != 0x82:
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
    """
    BVLL encoder (downstream LPDU to PDU) and decoder (upstream PDU to LPDU).
    """

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

    fdAddress: IPv6Address
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
class Result(LPDU):

    _debug_contents: Tuple[str, ...] = (
        "bvlciSourceVirtualAddress",
        "bvlciResultCode",
    )

    bvlciFunction = LPCI.result

    def __init__(
        self, source_virtual_address: VirtualAddress, result_code: int, *args, **kwargs
    ) -> None:
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 9
        self.bvlciSourceVirtualAddress = source_virtual_address
        self.bvlciResultCode = result_code

    def encode(self) -> PDU:
        if _debug:
            Result._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_short(self.bvlciResultCode)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            Result._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        result_code = pdu.get_short()

        return Result(source_virtual_address, result_code)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(
                ("source_virtual_address", self.bvlciSourceVirtualAddress),
                ("result_code", self.bvlciResultCode),
            ),
        )


#
#   OriginalUnicastNPDU
#


@register_bvlpdu_type
class OriginalUnicastNPDU(LPDU):
    _debug_contents: Tuple[str, ...] = (
        "bvlciSourceVirtualAddress",
        "bvlciDestinationVirtualAddress",
    )

    bvlciFunction = LPCI.originalUnicastNPDU

    def __init__(
        self,
        source_virtual_address: VirtualAddress,
        destination_virtual_address: VirtualAddress,
        *args,
        **kwargs,
    ) -> None:
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 10 + len(self.pduData)
        self.bvlciSourceVirtualAddress = source_virtual_address
        self.bvlciDestinationVirtualAddress = destination_virtual_address

    def encode(self) -> PDU:
        if _debug:
            OriginalUnicastNPDU._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr
        assert self.bvlciDestinationVirtualAddress.addrAddr

        self.bvlciLength = 10 + len(self.pduData)

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_data(self.bvlciDestinationVirtualAddress.addrAddr)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            OriginalUnicastNPDU._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        destination_virtual_address = VirtualAddress(pdu.get_data(3))
        data = pdu.get_data(len(pdu.pduData))

        return OriginalUnicastNPDU(
            source_virtual_address, destination_virtual_address, data
        )

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

    _debug_contents: Tuple[str, ...] = ("bvlciSourceVirtualAddress",)

    bvlciFunction = LPCI.originalBroadcastNPDU

    def __init__(self, source_virtual_address: VirtualAddress, *args, **kwargs) -> None:
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 7 + len(self.pduData)
        self.bvlciSourceVirtualAddress = source_virtual_address

    def encode(self) -> PDU:
        if _debug:
            OriginalBroadcastNPDU._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr

        self.bvlciLength = 7 + len(self.pduData)

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            OriginalBroadcastNPDU._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        data = pdu.get_data(len(pdu.pduData))

        return OriginalBroadcastNPDU(source_virtual_address, data)

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


#
#   AddressResolution
#


@register_bvlpdu_type
class AddressResolution(LPDU):
    _debug_contents: Tuple[str, ...] = (
        "bvlciSourceVirtualAddress",
        "bvlciTargetVirtualAddress",
    )

    bvlciFunction = LPCI.addressResolution

    def __init__(
        self,
        source_virtual_address: VirtualAddress,
        target_virtual_address: VirtualAddress,
        *args,
        **kwargs,
    ) -> None:
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 10
        self.bvlciSourceVirtualAddress = source_virtual_address
        self.bvlciTargetVirtualAddress = target_virtual_address

    def encode(self) -> PDU:
        if _debug:
            AddressResolution._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr
        assert self.bvlciTargetVirtualAddress.addrAddr

        self.bvlciLength = 10

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_data(self.bvlciTargetVirtualAddress.addrAddr)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            AddressResolution._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        target_virtual_address = VirtualAddress(pdu.get_data(3))

        return AddressResolution(source_virtual_address, target_virtual_address)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "AddressResolution"),),
        )

        # return what we built/updated
        return use_dict


#
#   ForwardedAddressResolution
#


@register_bvlpdu_type
class ForwardedAddressResolution(LPDU):
    _debug_contents: Tuple[str, ...] = (
        "bvlciOriginalSourceVirtualAddress",
        "bvlciTargetVirtualAddress",
        "bvlciOriginalSourceIPv6Address",
    )

    bvlciFunction = LPCI.forwardedAddressResolution

    def __init__(
        self,
        original_source_virtual_address: VirtualAddress,
        target_virtual_address: VirtualAddress,
        original_source_ipv6_address: IPv6Address,
        *args,
        **kwargs,
    ) -> None:
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 0x1C
        self.bvlciOriginalSourceVirtualAddress = original_source_virtual_address
        self.bvlciTargetVirtualAddress = target_virtual_address
        self.bvlciOriginalSourceIPv6Address = original_source_ipv6_address

    def encode(self) -> PDU:
        if _debug:
            ForwardedAddressResolution._debug("encode")
        assert self.bvlciOriginalSourceVirtualAddress.addrAddr
        assert self.bvlciTargetVirtualAddress.addrAddr
        assert self.bvlciOriginalSourceIPv6Address.addrAddr

        self.bvlciLength = 0x1C

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciOriginalSourceVirtualAddress.addrAddr)
        pdu.put_data(self.bvlciTargetVirtualAddress.addrAddr)
        pdu.put_data(self.bvlciOriginalSourceIPv6Address.addrAddr)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            ForwardedAddressResolution._debug("decode %r", pdu)

        original_source_virtual_address = VirtualAddress(pdu.get_data(3))
        target_virtual_address = VirtualAddress(pdu.get_data(3))
        original_source_ipv6_address = IPv6Address(pdu.get_data(18))

        return ForwardedAddressResolution(
            original_source_virtual_address,
            target_virtual_address,
            original_source_ipv6_address,
        )

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "ForwardedAddressResolution"),),
        )

        # return what we built/updated
        return use_dict


#
#   AddressResolutionACK
#


@register_bvlpdu_type
class AddressResolutionACK(LPDU):
    _debug_contents: Tuple[str, ...] = (
        "bvlciSourceVirtualAddress",
        "bvlciDestinationVirtualAddress",
    )

    bvlciFunction = LPCI.addressResolutionACK

    def __init__(
        self,
        source_virtual_address: VirtualAddress,
        destination_virtual_address: VirtualAddress,
        *args,
        **kwargs,
    ):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 10
        self.bvlciSourceVirtualAddress = source_virtual_address
        self.bvlciDestinationVirtualAddress = destination_virtual_address

    def encode(self) -> PDU:
        if _debug:
            AddressResolutionACK._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr
        assert self.bvlciDestinationVirtualAddress.addrAddr

        self.bvlciLength = 10

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_data(self.bvlciDestinationVirtualAddress.addrAddr)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            AddressResolutionACK._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        destination_virtual_address = VirtualAddress(pdu.get_data(3))

        return AddressResolutionACK(source_virtual_address, destination_virtual_address)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "AddressResolutionACK"),),
        )

        # return what we built/updated
        return use_dict


#
#   VirtualAddressResolution
#


@register_bvlpdu_type
class VirtualAddressResolution(LPDU):
    _debug_contents: Tuple[str, ...] = ("bvlciSourceVirtualAddress",)

    bvlciFunction = LPCI.virtualAddressResolution

    def __init__(
        self,
        source_virtual_address: VirtualAddress,
        *args,
        **kwargs,
    ):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 7
        self.bvlciSourceVirtualAddress = source_virtual_address

    def encode(self) -> PDU:
        if _debug:
            VirtualAddressResolution._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr

        self.bvlciLength = 7

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            VirtualAddressResolution._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))

        return VirtualAddressResolution(source_virtual_address)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "AddressResolutionACK"),),
        )

        # return what we built/updated
        return use_dict


#
#   VirtualAddressResolutionACK
#


@register_bvlpdu_type
class VirtualAddressResolutionACK(LPDU):
    _debug_contents: Tuple[str, ...] = (
        "bvlciSourceVirtualAddress",
        "bvlciDestinationVirtualAddress",
    )

    bvlciFunction = LPCI.virtualAddressResolutionACK

    def __init__(
        self,
        source_virtual_address: VirtualAddress,
        destination_virtual_address: VirtualAddress,
        *args,
        **kwargs,
    ):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 10
        self.bvlciSourceVirtualAddress = source_virtual_address
        self.bvlciDestinationVirtualAddress = destination_virtual_address

    def encode(self) -> PDU:
        if _debug:
            VirtualAddressResolutionACK._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr
        assert self.bvlciDestinationVirtualAddress.addrAddr

        self.bvlciLength = 10

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_data(self.bvlciDestinationVirtualAddress.addrAddr)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            VirtualAddressResolutionACK._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        destination_virtual_address = VirtualAddress(pdu.get_data(3))

        return AddressResolutionACK(source_virtual_address, destination_virtual_address)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "AddressResolutionACK"),),
        )

        # return what we built/updated
        return use_dict


#
#   ForwardedNPDU
#


@register_bvlpdu_type
class ForwardedNPDU(LPDU):

    _debug_contents: Tuple[str, ...] = (
        "bvlciSourceVirtualAddress",
        "bvlciSourceIPv6Address",
    )

    bvlciFunction = LPCI.forwardedNPDU

    def __init__(
        self,
        source_virtual_address: VirtualAddress,
        source_ipv6_address: IPv6Address,
        *args,
        **kwargs,
    ) -> None:
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 25 + len(self.pduData)
        self.bvlciSourceVirtualAddress = source_virtual_address
        self.bvlciSourceIPv6Address = source_ipv6_address

    def encode(self) -> PDU:
        if _debug:
            ForwardedNPDU._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr
        assert self.bvlciSourceIPv6Address.addrAddr

        # make sure the length is correct
        self.bvlciLength = 25 + len(self.pduData)

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_data(self.bvlciSourceIPv6Address.addrAddr)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            ForwardedNPDU._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        source_ipv6_address = IPv6Address(pdu.get_data(18))
        data = pdu.get_data(len(pdu.pduData))

        return ForwardedNPDU(source_virtual_address, source_ipv6_address, data)

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
                ("source_virtual_address", self.bvlciSourceVirtualAddress),
                ("source_ipv6_address", self.bvlciSourceIPv6Address),
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
    _debug_contents: Tuple[str, ...] = (
        "bvlciSourceVirtualAddress",
        "bvlciTimeToLive",
    )

    bvlciFunction = LPCI.registerForeignDevice

    def __init__(
        self,
        source_virtual_address: VirtualAddress,
        time_to_live: int,
        *args,
        **kwargs,
    ):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 9
        self.bvlciSourceVirtualAddress = source_virtual_address
        self.bvlciTimeToLive = time_to_live

    def encode(self) -> PDU:
        if _debug:
            RegisterForeignDevice._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr

        self.bvlciLength = 9

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_short(self.bvlciTimeToLive)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            RegisterForeignDevice._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        time_to_live = pdu.get_short()

        return RegisterForeignDevice(source_virtual_address, time_to_live)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "RegisterForeignDevice"),),
        )

        # return what we built/updated
        return use_dict


#
#   DeleteForeignDeviceTableEntry
#


@register_bvlpdu_type
class DeleteForeignDeviceTableEntry(LPDU):
    _debug_contents: Tuple[str, ...] = (
        "bvlciSourceVirtualAddress",
        "bvlciFDTEntry",
    )

    bvlciFunction = LPCI.deleteForeignDeviceTableEntry

    def __init__(
        self,
        source_virtual_address: VirtualAddress,
        fdt_entry: IPv6Address,
        *args,
        **kwargs,
    ):
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 25
        self.bvlciSourceVirtualAddress = source_virtual_address
        self.bvlciFDTEntry = fdt_entry

    def encode(self) -> PDU:
        if _debug:
            DeleteForeignDeviceTableEntry._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr
        assert self.bvlciFDTEntry.addrAddr

        self.bvlciLength = 25

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_data(self.bvlciFDTEntry.addrAddr)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            DeleteForeignDeviceTableEntry._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        fdt_entry = IPv6Address(pdu.get_data(18))

        return DeleteForeignDeviceTableEntry(source_virtual_address, fdt_entry)

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""

        # make/extend the dictionary of content
        if use_dict is None:
            use_dict = as_class()

        # call the normal procedure
        key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("function", "DeleteForeignDeviceTableEntry"),),
        )

        # return what we built/updated
        return use_dict


#
#   DistributeBroadcastToNetwork
#


@register_bvlpdu_type
class DistributeBroadcastToNetwork(LPDU):

    _debug_contents: Tuple[str, ...] = (
        "bvlciSourceVirtualAddress",
        "bvlciSourceIPv6Address",
    )

    bvlciFunction = LPCI.distributeBroadcastToNetwork

    def __init__(
        self,
        source_virtual_address: VirtualAddress,
        *args,
        **kwargs,
    ) -> None:
        LPDU.__init__(self, *args, **kwargs)

        self.bvlciLength = 7 + len(self.pduData)
        self.bvlciSourceVirtualAddress = source_virtual_address

    def encode(self) -> PDU:
        if _debug:
            DistributeBroadcastToNetwork._debug("encode")
        assert self.bvlciSourceVirtualAddress.addrAddr

        # make sure the length is correct
        self.bvlciLength = 7 + len(self.pduData)

        pdu = LPCI.encode(self)
        pdu.put_data(self.bvlciSourceVirtualAddress.addrAddr)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            DistributeBroadcastToNetwork._debug("decode %r", pdu)

        source_virtual_address = VirtualAddress(pdu.get_data(3))
        data = pdu.get_data(len(pdu.pduData))

        return DistributeBroadcastToNetwork(source_virtual_address, data)

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
                ("source_virtual_address", self.bvlciSourceVirtualAddress),
                ("source_ipv6_address", self.bvlciSourceIPv6Address),
            ),
        )

        # this message has data
        PDUData.dict_contents(self, use_dict=use_dict, as_class=as_class)

        # return what we built/updated
        return use_dict
