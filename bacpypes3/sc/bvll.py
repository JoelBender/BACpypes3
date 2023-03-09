"""
BACnet Secure Connect Virtual Link Layer Protocol Data Units
"""

from __future__ import annotations

import socket
from uuid import UUID
from typing import Callable, List, Optional, Tuple, Union, cast

from ..errors import EncodingError, DecodingError
from ..debugging import ModuleLogger, DebugContents, bacpypes_debugging

from ..pdu import IPv6Address, VirtualAddress, PCI, PDUData, PDU
from ..comm import Client, Server
from ..basetypes import ErrorClass, ErrorCode

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# a dictionary of functions and LPDU classes
pdu_types = {}


def register_bvlpdu_type(class_):
    pdu_types[class_.bvlcFunction] = class_
    return class_


#
#   HeaderOption
#


@bacpypes_debugging
class HeaderOption(PDUData, DebugContents):
    """
    Header Option
    """

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "option_type",
        "header_data_flag",
        "must_understand",
        "more_options",
        "header_marker",
        "header_length",
    )
    debug_contents = DebugContents.debug_contents  # type: ignore[assignment]

    option_type: int = 0
    header_data_flag: bool = False
    must_understand: bool = False
    more_options: bool = False

    header_marker: int = 0
    header_length: int = 0

    def __init__(
        self,
        *args,
        option_type: int = 0,
        header_data_flag: bool = False,
        must_understand: bool = False,
        more_options: bool = False,
        **kwargs,
    ) -> None:
        if _debug:
            HeaderOption._debug(
                "__init__ %r option_type=%r header_data_flag=%r must_understand=%r more_options=%r",
                args,
                option_type,
                header_data_flag,
                must_understand,
                more_options,
            )
        PDUData.__init__(self, *args)

        self.option_type = option_type
        self.header_data_flag = header_data_flag
        self.must_understand = must_understand
        self.more_options = more_options

        # if there is header data, set the flag and the length
        if self.pduData:
            self.header_data_flag = True
            self.header_length = len(self.pduData)

        # make sure the marker is correct
        header_marker = self.option_type & 0x1F
        if self.header_data_flag:
            header_marker |= 0x20
        if self.must_understand:
            header_marker |= 0x40
        if self.more_options:
            header_marker |= 0x80
        self.header_marker = header_marker

    def encode(self) -> PDU:
        """Encode the contents of the HeaderOption into a PDU."""
        if _debug:
            HeaderOption._debug("encode")

        pdu = PDU()

        # make sure the length and flags are correct, assume that must_understand
        # and more_options are set correctly
        if self.option_type == 1:  # SecurePathHeaderOption
            self.header_data_flag = False
            self.header_length = 0

        elif self.option_type == 31:  # ProprietaryHeaderOption
            self.header_data_flag = True
            self.header_length = 3 + len(self.pduData)

        else:  # HeaderOption
            if self.pduData:
                self.header_data_flag = True
                self.header_length = len(self.pduData)
            else:
                self.header_data_flag = False
                self.header_length = 0

        # make sure the marker is correct
        header_marker = self.option_type & 0x1F
        if self.header_data_flag:
            header_marker |= 0x20
        if self.must_understand:
            header_marker |= 0x40
        if self.more_options:
            header_marker |= 0x80
        self.header_marker = header_marker

        pdu.put(header_marker)
        if self.header_data_flag:
            pdu.put_short(self.header_length)

        if self.option_type == 1:
            pass

        elif self.option_type == 31:
            hpdu = cast(ProprietaryHeaderOption, self)
            pdu.put_short(hpdu.vendor_identifier)
            pdu.put(hpdu.proprietary_option_type)
            pdu.put_data(hpdu.pduData)

        else:
            if self.header_data_flag:
                pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> HeaderOption:
        """
        Decode the contents of the PDU and return a HeaderOption or one
        of its subclasses.
        """
        if _debug:
            HeaderOption._debug("decode %r", pdu)

        # extract the marker, pull out the contents
        header_marker = pdu.get()

        option_type = header_marker & 0x1F
        header_data_flag = bool(header_marker & 0x20)

        header_length: int = 0
        if header_data_flag:
            header_length = pdu.get_short()

        # deeper decode
        hpdu: HeaderOption
        if option_type == 1:
            hpdu = SecurePathHeaderOption()

        elif option_type == 31:
            hpdu = ppdu = ProprietaryHeaderOption()
            ppdu.vendor_identifier = pdu.get_short()
            ppdu.proprietary_option_type = pdu.get()
            ppdu.put_data(pdu.get_data(header_length - 3))

        else:
            hpdu = HeaderOption()
            if header_data_flag:
                hpdu.put_data(pdu.get_data(header_length))

        # update the HPDU with the header stuff
        hpdu.header_marker = header_marker
        hpdu.header_length = header_length

        hpdu.option_type = header_marker & 0x1F
        hpdu.header_data_flag = bool(header_marker & 0x20)
        hpdu.must_understand = bool(header_marker & 0x40)
        hpdu.more_options = bool(header_marker & 0x80)
        hpdu.header_length = header_length

        return hpdu


class SecurePathHeaderOption(HeaderOption):
    def __init__(self):
        if _debug:
            HeaderOption._debug("__init__")
        HeaderOption.__init__(self, option_type=1, must_understand=True)


class ProprietaryHeaderOption(HeaderOption):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = ("vendor_identifier", "proprietary_option_type")

    vendor_identifier: int = 0
    proprietary_option_type: int = 0

    def __init__(
        self,
        *args,
        vendor_identifier: int = 0,
        proprietary_option_type: int = 0,
        **kwargs,
    ):
        if _debug:
            ProprietaryHeaderOption._debug(
                "__init__ %r %r", vendor_identifier, proprietary_option_type
            )
        HeaderOption.__init__(self, *args, option_type=31, **kwargs)

        self.vendor_identifier = vendor_identifier
        self.proprietary_option_type = proprietary_option_type

        # override the header length calculation
        self.header_length = 3 + len(self.pduData)


#
#   LPCI
#


@bacpypes_debugging
class LPCI(PCI, DebugContents):
    """
    Link Layer Protocol Control Information
    """

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "bvlcFunction",
        "bvlcControlFlags",
        "bvlcMessageID",
        "bvlcOriginatingVirtualAddress",
        "bvlcDestinationVirtualAddress",
        "bvlcDestinationOptions+",
        "bvlcDataOptions+",
    )

    result = 0x00
    encapsulatedNPDU = 0x01
    addressResolution = 0x02
    addressResolutionACK = 0x03
    advertisement = 0x04
    advertisementSolicitation = 0x05
    connectRequest = 0x06
    connectAccept = 0x07
    disconnectRequest = 0x08
    disconnectACK = 0x09
    heartbeatRequest = 0x0A
    heartbeatACK = 0x0B
    proprietaryMessage = 0x0C

    bvlcFunction: int
    bvlcControlFlags: int
    bvlcMessageID: int
    bvlcOriginatingVirtualAddress: Optional[VirtualAddress] = None
    bvlcDestinationVirtualAddress: Optional[VirtualAddress] = None
    bvlcDestinationOptions: List[HeaderOption]
    bvlcDataOptions: List[HeaderOption]

    def __init__(self, *args, **kwargs) -> None:
        if _debug:
            LPCI._debug("__init__ %r %r", args, kwargs)
        PCI.__init__(self, *args, **kwargs)

        self.bvlcDestinationOptions = []
        self.bvlcDataOptions = []

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

        # save the function
        pdu.put(self.bvlcFunction)

        control_flags = 0
        if self.bvlcOriginatingVirtualAddress is not None:
            control_flags |= 0x08
        if self.bvlcDestinationVirtualAddress is not None:
            control_flags |= 0x04
        if self.bvlcDestinationOptions:
            control_flags |= 0x02
        if self.bvlcDataOptions:
            control_flags |= 0x01
        self.bvlcControlFlags = control_flags

        pdu.put(control_flags)
        pdu.put_short(self.bvlcMessageID)

        if self.bvlcOriginatingVirtualAddress is not None:
            pdu.put_data(self.bvlcOriginatingVirtualAddress.addrAddr)  # type: ignore[arg-type]
        if self.bvlcDestinationVirtualAddress is not None:
            pdu.put_data(self.bvlcDestinationVirtualAddress.addrAddr)  # type: ignore[arg-type]

        # make sure the more options flags are set correctly
        if self.bvlcDestinationOptions:
            for header in self.bvlcDestinationOptions[:-1]:
                header.more_options = True
            self.bvlcDestinationOptions[-1].more_options = False
        if self.bvlcDataOptions:
            for header in self.bvlcDataOptions[:-1]:
                header.more_options = True
            self.bvlcDataOptions[-1].more_options = False

        # destination and data header options
        for header in self.bvlcDestinationOptions:
            header_pdu = header.encode()
            pdu.put_data(header_pdu.pduData)
        for header in self.bvlcDataOptions:
            header_pdu = header.encode()
            pdu.put_data(header_pdu.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPCI:
        """Decode the contents of the PDU and return a LPCI."""
        if _debug:
            LPCI._debug("decode %r %r", class_, pdu)

        lpci = LPCI()
        PCI.update(lpci, pdu)

        lpci.bvlcFunction = pdu.get()

        control_flags = pdu.get()
        has_originating_virtual_address = control_flags & 0x08
        has_destination_virtual_address = control_flags & 0x04
        has_destination_options = control_flags & 0x02
        has_data_options = control_flags & 0x08
        lpci.bvlcControlFlags = control_flags

        lpci.bvlcMessageID = pdu.get_short()

        if has_originating_virtual_address:
            lpci.bvlcOriginatingVirtualAddress = VirtualAddress(pdu.get_data(6))
        if has_destination_virtual_address:
            lpci.bvlcDestinationVirtualAddress = VirtualAddress(pdu.get_data(6))

        if has_destination_options:
            while True:
                header_marker = pdu.pduData[0]
                more_options = header_marker & 0x80

                header = HeaderOption.decode(pdu)
                lpci.bvlcDestinationOptions.append(header)

                if not more_options:
                    break

        if has_data_options:
            while True:
                header_marker = pdu.pduData[0]
                more_options = header_marker & 0x80

                header = HeaderOption.decode(pdu)
                lpci.bvlcDataOptions.append(header)

                if not more_options:
                    break

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
        pdu: PDU = lpdu.encode()
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
            lpdu_class = pdu_types[lpci.bvlcFunction]
        except KeyError:
            raise DecodingError(f"unrecognized BVLL function: {lpci.bvlcFunction}")
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
#   Result
#


@register_bvlpdu_type
class Result(LPDU):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "result_function",
        "result_code",
        "error_header_marker",
        "error_class",
        "error_code",
        "error_details",
    )

    bvlcFunction = LPCI.result

    result_function: int
    result_code: int
    error_header_marker: int
    error_class: ErrorClass
    error_code: ErrorCode
    error_details: str

    def __init__(
        self,
        result_function: int,
        result_code: int,
        error_header_marker: int = 0,
        error_class: Optional[ErrorClass] = None,
        error_code: Optional[ErrorCode] = None,
        error_details: str = "",
        *args,
        **kwargs,
    ) -> None:
        if _debug:
            Result._debug("__init__ %r %r", args, kwargs)
        LPDU.__init__(self, *args, **kwargs)

        self.result_function = result_function
        self.result_code = result_code
        if result_code == 0x00:  # ACK
            if error_class is not None:
                raise RuntimeError(
                    f"invalid error_class parameter with ACK: {error_class}"
                )
            if error_code is not None:
                raise RuntimeError(
                    f"invalid error_code parameter with ACK: {error_code}"
                )
        elif result_code == 0x01:  # NACK
            self.error_header_marker = error_header_marker

            if error_class is None:
                raise RuntimeError("error_class parameter required")
            self.error_class = error_class

            if error_code is None:
                raise RuntimeError("error_code parameter required")
            self.error_code = error_code

            self.error_details = error_details
        else:
            raise RuntimeError(f"invalid result code: {result_code}")

    def encode(self) -> PDU:
        if _debug:
            Result._debug("encode")

        pdu = LPCI.encode(self)
        pdu.put(self.result_function)
        pdu.put(self.result_code)

        if self.result_code:
            pdu.put(self.error_header_marker)
            pdu.put_short(self.error_class)
            pdu.put_short(self.error_code)
            pdu.put_data(self.error_details.encode("utf-8"))

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            Result._debug("decode %r", pdu)

        result_function = pdu.get()
        result_code = pdu.get()
        if result_code == 0x00:  # ACK
            return Result(result_function=result_function, result_code=result_code)

        elif result_code == 0x01:  # NACK
            error_header_marker = pdu.get()
            error_class = ErrorClass(pdu.get_short())
            error_code = ErrorCode(pdu.get_short())

            if not pdu.pduData:
                error_details = ""
            else:
                error_details = pdu.get_data(len(pdu.pduData)).decode("utf-8")

            return Result(
                result_function=result_function,
                result_code=result_code,
                error_header_marker=error_header_marker,
                error_class=error_class,
                error_code=error_code,
                error_details=error_details,
            )
        else:
            raise RuntimeError(f"invalid result code: {result_code}")

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("tbd", "tbd"),),
        )


#
#   EncapsulatedNPDU
#


@register_bvlpdu_type
class EncapsulatedNPDU(LPDU):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = ()

    bvlcFunction = LPCI.encapsulatedNPDU

    def __init__(self, *args, **kwargs) -> None:
        if _debug:
            EncapsulatedNPDU._debug("__init__ %r %r", args, kwargs)
        LPDU.__init__(self, *args, **kwargs)

    def encode(self) -> PDU:
        if _debug:
            EncapsulatedNPDU._debug("encode")

        pdu = LPCI.encode(self)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            EncapsulatedNPDU._debug("decode %r", pdu)

        lpdu = EncapsulatedNPDU()
        lpdu.put_data(pdu.get_data(len(pdu.pduData)))

        return lpdu

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("tbd", "tbd"),),
        )


#
#   AddressResolution
#


@register_bvlpdu_type
class AddressResolution(LPDU):

    bvlcFunction = LPCI.addressResolution

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            AddressResolution._debug("decode %r", pdu)

        return AddressResolution()


#
#   AddressResolutionACK
#


@register_bvlpdu_type
class AddressResolutionACK(LPDU):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = ("websocket_uris",)

    bvlcFunction = LPCI.addressResolutionACK

    websocket_uris: str

    def __init__(self, websocket_uris: str = "", *args, **kwargs) -> None:
        if _debug:
            AddressResolutionACK._debug(
                "__init__ %r %r %r", websocket_uris, args, kwargs
            )
        LPDU.__init__(self, *args, **kwargs)

        self.websocket_uris = websocket_uris

    def encode(self) -> PDU:
        if _debug:
            EncapsulatedNPDU._debug("encode")

        pdu = LPCI.encode(self)
        pdu.put_data(self.websocket_uris.encode("utf-8"))

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            AddressResolutionACK._debug("decode %r", pdu)

        lpdu = AddressResolutionACK()

        if not pdu.pduData:
            lpdu.websocket_uris = ""
        else:
            lpdu.websocket_uris = pdu.get_data(len(pdu.pduData)).decode("utf-8")

        return lpdu

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("tbd", "tbd"),),
        )


#
#   Advertisement
#


@register_bvlpdu_type
class Advertisement(LPDU):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "hub_connection_status",
        "accept_direct_connections",
        "maximum_bvlc_length",
        "maximum_npdu_length",
    )

    bvlcFunction = LPCI.advertisement

    hub_connection_status: int
    accept_direct_connections: int
    maximum_bvlc_length: int
    maximum_npdu_length: int

    def __init__(
        self,
        hub_connection_status: int,
        accept_direct_connections: int,
        maximum_bvlc_length: int,
        maximum_npdu_length: int,
        *args,
        **kwargs,
    ) -> None:
        if _debug:
            Advertisement._debug(
                "__init__ %r %r %r %r %r %r",
                hub_connection_status,
                accept_direct_connections,
                maximum_bvlc_length,
                maximum_npdu_length,
                args,
                kwargs,
            )
        LPDU.__init__(self, *args, **kwargs)

        self.hub_connection_status = hub_connection_status
        self.accept_direct_connections = accept_direct_connections
        self.maximum_bvlc_length = maximum_bvlc_length
        self.maximum_npdu_length = maximum_npdu_length

    def encode(self) -> PDU:
        if _debug:
            Advertisement._debug("encode")

        pdu = LPCI.encode(self)
        pdu.put(self.hub_connection_status)
        pdu.put(self.accept_direct_connections)
        pdu.put_short(self.maximum_bvlc_length)
        pdu.put_short(self.maximum_npdu_length)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            Advertisement._debug("decode %r", pdu)

        hub_connection_status = pdu.get()
        accept_direct_connections = pdu.get()
        maximum_bvlc_length = pdu.get_short()
        maximum_npdu_length = pdu.get_short()

        return Advertisement(
            hub_connection_status=hub_connection_status,
            accept_direct_connections=accept_direct_connections,
            maximum_bvlc_length=maximum_bvlc_length,
            maximum_npdu_length=maximum_npdu_length,
        )

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("tbd", "tbd"),),
        )


#
#   AdvertisementSolicitation
#


@register_bvlpdu_type
class AdvertisementSolicitation(LPDU):

    bvlcFunction = LPCI.advertisementSolicitation

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            AdvertisementSolicitation._debug("decode %r", pdu)

        return AdvertisementSolicitation()


#
#   ConnectRequest
#


@register_bvlpdu_type
class ConnectRequest(LPDU):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "vmac_address",
        "device_uuid",
        "maximum_bvlc_length",
        "maximum_npdu_length",
    )

    bvlcFunction = LPCI.connectRequest

    vmac_address: VirtualAddress
    device_uuid: UUID
    maximum_bvlc_length: int
    maximum_npdu_length: int

    def __init__(
        self,
        vmac_address: VirtualAddress,
        device_uuid: UUID,
        maximum_bvlc_length: int,
        maximum_npdu_length: int,
        *args,
        **kwargs,
    ) -> None:
        if _debug:
            ConnectRequest._debug("__init__ %r %r %r", kwargs)
        LPDU.__init__(self, **kwargs)

        if not isinstance(vmac_address, VirtualAddress):
            raise TypeError("vmac_address")
        if len(vmac_address.addrAddr) != 6:  # type: ignore[arg-type]
            raise ValueError("vmac_address length")
        self.vmac_address = vmac_address

        if not isinstance(device_uuid, UUID):
            raise TypeError("device_uuid")
        self.device_uuid = device_uuid

        self.maximum_bvlc_length = maximum_bvlc_length
        self.maximum_npdu_length = maximum_npdu_length

    def encode(self) -> PDU:
        if _debug:
            ConnectRequest._debug("encode")

        pdu = LPCI.encode(self)
        pdu.put_data(self.vmac_address.addrAddr)  # type: ignore[arg-type]
        pdu.put_data(self.device_uuid.bytes)
        pdu.put_short(self.maximum_bvlc_length)
        pdu.put_short(self.maximum_npdu_length)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            ConnectRequest._debug("decode %r", pdu)

        vmac_address = VirtualAddress(pdu.get_data(6))
        device_uuid = UUID(bytes=bytes(pdu.get_data(16)))
        maximum_bvlc_length = pdu.get_short()
        maximum_npdu_length = pdu.get_short()

        return ConnectRequest(
            vmac_address=vmac_address,
            device_uuid=device_uuid,
            maximum_bvlc_length=maximum_bvlc_length,
            maximum_npdu_length=maximum_npdu_length,
        )

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("tbd", "tbd"),),
        )


#
#   ConnectAccept
#


@register_bvlpdu_type
class ConnectAccept(LPDU):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "vmac_address",
        "device_uuid",
        "maximum_bvlc_length",
        "maximum_npdu_length",
    )

    bvlcFunction = LPCI.connectAccept

    vmac_address: VirtualAddress
    device_uuid: UUID
    maximum_bvlc_length: int
    maximum_npdu_length: int

    def __init__(
        self,
        vmac_address: VirtualAddress,
        device_uuid: UUID,
        maximum_bvlc_length: int,
        maximum_npdu_length: int,
        *args,
        **kwargs,
    ) -> None:
        if _debug:
            ConnectAccept._debug("__init__ %r %r %r", kwargs)
        LPDU.__init__(self, **kwargs)

        if not isinstance(vmac_address, VirtualAddress):
            raise TypeError("vmac_address")
        if len(vmac_address.addrAddr) != 6:  # type: ignore[arg-type]
            raise ValueError("vmac_address length")
        self.vmac_address = vmac_address

        if not isinstance(device_uuid, UUID):
            raise TypeError("device_uuid")
        self.device_uuid = device_uuid

        self.maximum_bvlc_length = maximum_bvlc_length
        self.maximum_npdu_length = maximum_npdu_length

    def encode(self) -> PDU:
        if _debug:
            ConnectAccept._debug("encode")

        pdu = LPCI.encode(self)
        pdu.put_data(self.vmac_address.addrAddr)  # type: ignore[arg-type]
        pdu.put_data(self.device_uuid.bytes)
        pdu.put_short(self.maximum_bvlc_length)
        pdu.put_short(self.maximum_npdu_length)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            ConnectAccept._debug("decode %r", pdu)

        vmac_address = VirtualAddress(pdu.get_data(6))
        device_uuid = UUID(bytes=bytes(pdu.get_data(16)))
        maximum_bvlc_length = pdu.get_short()
        maximum_npdu_length = pdu.get_short()

        return ConnectAccept(
            vmac_address=vmac_address,
            device_uuid=device_uuid,
            maximum_bvlc_length=maximum_bvlc_length,
            maximum_npdu_length=maximum_npdu_length,
        )

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("tbd", "tbd"),),
        )


#
#   DisconnectRequest
#


@register_bvlpdu_type
class DisconnectRequest(LPDU):

    bvlcFunction = LPCI.disconnectRequest

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            DisconnectRequest._debug("decode %r", pdu)

        return DisconnectRequest()


#
#   DisconnectACK
#


@register_bvlpdu_type
class DisconnectACK(LPDU):

    bvlcFunction = LPCI.disconnectACK

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            DisconnectACK._debug("decode %r", pdu)

        return DisconnectACK()


#
#   HeartbeatRequest
#


@register_bvlpdu_type
class HeartbeatRequest(LPDU):

    bvlcFunction = LPCI.heartbeatRequest

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            HeartbeatRequest._debug("decode %r", pdu)

        return HeartbeatRequest()


#
#   HeartbeatACK
#


@register_bvlpdu_type
class HeartbeatACK(LPDU):

    bvlcFunction = LPCI.heartbeatACK

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            HeartbeatACK._debug("decode %r", pdu)

        return HeartbeatACK()


#
#   proprietaryMessage
#


@register_bvlpdu_type
class ProprietaryMessage(LPDU):

    _debug: Callable[..., None]
    _debug_contents: Tuple[str, ...] = (
        "vendor_identifier",
        "proprietary_function",
    )

    bvlcFunction = LPCI.proprietaryMessage

    vendor_identifier: int
    proprietary_function: int

    def __init__(
        self, vendor_identifier: int, proprietary_function: int, *args, **kwargs
    ) -> None:
        if _debug:
            ProprietaryMessage._debug("__init__ %r %r", args, kwargs)
        LPDU.__init__(self, *args, **kwargs)

        self.vendor_identifier = vendor_identifier
        self.proprietary_function = proprietary_function

    def encode(self) -> PDU:
        if _debug:
            ConnectAccept._debug("encode")

        pdu = LPCI.encode(self)
        pdu.put_short(self.vendor_identifier)
        pdu.put(self.proprietary_function)
        pdu.put_data(self.pduData)

        return pdu

    @classmethod
    def decode(class_, pdu: PDU) -> LPDU:  # type: ignore[override]
        if _debug:
            ConnectAccept._debug("decode %r", pdu)

        vendor_identifier = pdu.get_short()
        proprietary_function = pdu.get()
        proprietary_data = pdu.get_data(len(pdu.pduData))

        return ProprietaryMessage(
            vendor_identifier,
            proprietary_function,
            proprietary_data,
        )

    def lpdu_contents(self, use_dict=None, as_class=dict):
        """Return the contents of an object as a dict."""
        return key_value_contents(
            use_dict=use_dict,
            as_class=as_class,
            key_values=(("tbd", "tbd"),),
        )
