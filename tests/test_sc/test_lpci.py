"""
Test BACnet/SC LPCI
-------------------
"""

import pytest

from bacpypes3.debugging import ModuleLogger
from bacpypes3.pdu import PDU

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
