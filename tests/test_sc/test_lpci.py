"""
Test BACnet/SC LPCI
-------------------
"""

import pytest

from bacpypes3.debugging import ModuleLogger
from bacpypes3.pdu import PDU, VirtualAddress

sc_bvll = pytest.importorskip("bacpypes3.sc.bvll")
LPCI = sc_bvll.LPCI
EncapsulatedNPDU = sc_bvll.EncapsulatedNPDU
HeaderOption = sc_bvll.HeaderOption
pdu_types = sc_bvll.pdu_types

# some debugging
_debug = 0
_log = ModuleLogger(globals())

NPDU = bytes.fromhex("0100")


def header_option(option_type: int) -> HeaderOption:
    header = HeaderOption()
    header.option_type = option_type
    header.must_understand = False
    header.header_data_flag = False
    return header


def codec_decode(pdu: PDU):
    """Decode the same way BVLLCodec.confirmation does."""
    lpci = LPCI.decode(pdu)
    lpdu = pdu_types[lpci.bvlcFunction].decode(pdu)
    LPCI.update(lpdu, lpci)
    return lpdu


def test_update_copies_destination_options():
    lpdu = EncapsulatedNPDU(NPDU)
    lpdu.bvlcMessageID = 1
    lpdu.bvlcDestinationOptions = [header_option(2), header_option(3)]

    decoded = codec_decode(lpdu.encode())

    assert isinstance(decoded, EncapsulatedNPDU)
    assert [h.option_type for h in decoded.bvlcDestinationOptions] == [2, 3]
    assert decoded.bvlcDataOptions == []
    assert bytes(decoded.pduData) == NPDU


def test_update_copies_data_options():
    lpdu = EncapsulatedNPDU(NPDU)
    lpdu.bvlcMessageID = 1
    lpdu.bvlcDataOptions = [header_option(2), header_option(3)]

    decoded = codec_decode(lpdu.encode())

    assert decoded.bvlcControlFlags == 0x01
    assert decoded.bvlcDestinationOptions == []
    assert [h.option_type for h in decoded.bvlcDataOptions] == [2, 3]
    assert bytes(decoded.pduData) == NPDU


def test_originating_address_without_data_options():
    """A hub-forwarded message has an originating virtual address but no
    data options; the NPDU must not be parsed as header options."""
    lpdu = EncapsulatedNPDU(NPDU)
    lpdu.bvlcMessageID = 1
    lpdu.bvlcOriginatingVirtualAddress = VirtualAddress(bytes(range(1, 7)))

    decoded = codec_decode(lpdu.encode())

    assert decoded.bvlcControlFlags == 0x08
    assert decoded.bvlcOriginatingVirtualAddress == VirtualAddress(bytes(range(1, 7)))
    assert decoded.bvlcDataOptions == []
    assert bytes(decoded.pduData) == NPDU


def test_all_flags():
    lpdu = EncapsulatedNPDU(NPDU)
    lpdu.bvlcMessageID = 1
    lpdu.bvlcOriginatingVirtualAddress = VirtualAddress(bytes(range(1, 7)))
    lpdu.bvlcDestinationVirtualAddress = VirtualAddress(bytes(range(11, 17)))
    lpdu.bvlcDestinationOptions = [header_option(2)]
    lpdu.bvlcDataOptions = [header_option(3), header_option(4)]

    decoded = codec_decode(lpdu.encode())

    assert decoded.bvlcControlFlags == 0x0F
    assert [h.option_type for h in decoded.bvlcDestinationOptions] == [2]
    assert [h.option_type for h in decoded.bvlcDataOptions] == [3, 4]
    assert bytes(decoded.pduData) == NPDU


def test_update_does_not_alias_option_lists():
    source = LPCI()
    source.bvlcDestinationOptions.append(header_option(2))

    target = LPCI()
    target.update(source)
    target.bvlcDestinationOptions.append(header_option(3))

    assert len(source.bvlcDestinationOptions) == 1


def test_lpci_contents_includes_options():
    lpci = LPCI()
    lpci.bvlcDestinationOptions.append(header_option(2))

    contents = lpci.lpci_contents()

    assert contents["bvlcDestinationOptions"] == lpci.bvlcDestinationOptions
    assert contents["bvlcDataOptions"] == []
