"""
Utility functions
"""

import base64
import binascii
from functools import partial

from typing import Any as _Any, List as _List, Dict

from ..pdu import Address
from ..errors import DecodingError
from ..debugging import bacpypes_debugging, ModuleLogger

from ..primitivedata import (
    attr_to_asn1,
    TagClass,
    TagNumber,
    Tag,
    ApplicationTag,
    OpeningTag,
    ClosingTag,
    ContextTag,
    TagList,
    Atomic,
    Null,
    Boolean,
    Unsigned,
    Integer,
    Real,
    Double,
    OctetString,
    CharacterString,
    BitString,
    Enumerated,
    Date,
    Time,
    ObjectIdentifier,
)
from ..constructeddata import (
    Any,  # covers AnyAtomic
    Sequence,  # covers both Sequence and Choice
    ExtendedList,  # covers SequenceOf, ArrayOf, and ListOf
)

from ..apdu import (
    PCI,
    APCI,
    APCISequence,
    APDU,
    confirmed_request_types,
    unconfirmed_request_types,
    complex_ack_types,
    error_types,
    ConfirmedRequestPDU,
    UnconfirmedRequestPDU,
    SimpleAckPDU,
    ComplexAckPDU,
    SegmentAckPDU,
    ErrorPDU,
    RejectPDU,
    AbortPDU,
)


# these dictionaries are restricted to what can be JSON encoded
JSONDict = Dict[str, _Any]

# some debugging
_debug = 0
_log = ModuleLogger(globals())


#
#   Primitive Data
#

_bitstring_as_bits = 0
_bitstring_as_str = 0
_bitstring_as_list = 1

_octetstring_as_base64Binary = 0
_octetstring_as_hexBinary = 1


def null_encode(value):
    return []


def null_decode(value, class_):
    assert isinstance(value, list) and len(value) == 0
    return class_(())


def boolean_encode(value):
    return bool(value)


def boolean_decode(value, class_):
    assert isinstance(value, bool)
    return class_(value)


def unsigned_encode(value):
    return int(value)


def unsigned_decode(value, class_):
    assert isinstance(value, int) and (value >= 0)
    return class_(value)


def integer_encode(value):
    return int(value)


def integer_decode(value, class_):
    assert isinstance(value, int)
    return class_(value)


def real_encode(value):
    return float(value)


def real_decode(value, class_):
    assert isinstance(value, float)
    return class_(value)


def double_encode(value):
    return float(value)


def double_decode(value, class_):
    assert isinstance(value, float)
    return class_(value)


def octetstring_encode(value):
    if _octetstring_as_base64Binary:
        return base64.b64encode(value).decode()

    if _octetstring_as_hexBinary:
        return binascii.hexlify(value).decode()

    raise NotImplementedError("octetstring_encode")


def octetstring_decode(value, class_):
    """
    This decoding function first attempts to decode the string content
    as base-64 or bin-hex to match the encoding function above, but
    has a backup for passing the value to the class, for example,
    IPv4OctetString is a subclass of OctetString that accepts IPv4 addresses.
    """
    _log.debug("octetstring_decode %r %r", value, class_)

    if _octetstring_as_base64Binary:
        assert isinstance(value, str)
        try:
            return class_(base64.b64decode(value))
        except Exception:
            return class_(value)

    if _octetstring_as_hexBinary:
        assert isinstance(value, str)
        try:
            return class_(binascii.unhexlify(value))
        except Exception:
            return class_(value)

    raise NotImplementedError("octetstring_decode")


def characterstring_encode(value):
    return str(value)


def characterstring_decode(value, class_):
    assert isinstance(value, str)
    return class_(value)


def bitstring_encode(value):
    if _bitstring_as_bits:
        return "".join(str(bit) for bit in value)

    if _bitstring_as_str:
        return str(value)

    if _bitstring_as_list:
        bit_names = {v: k for k, v in value._bitstring_names.items()}

        result = []
        for bit_number, bit in enumerate(value):
            if not bit:
                continue

            if bit_number in bit_names:
                result.append(bit_names[bit_number])
            else:
                result.append(bit_number)

        return result

    raise NotImplementedError("bitstring_encode")


def bitstring_decode(value, class_):
    if _bitstring_as_bits:
        assert isinstance(value, str)
        bit_string = [int(c) for c in str(value) if c in ("0", "1")]
        return class_(bit_string)

    if _bitstring_as_str:
        return class_(str(value))

    if _bitstring_as_list:
        assert isinstance(value, list)
        return class_(value)

    raise NotImplementedError("bitstring_decode")


def enumerated_encode(value):
    return value.asn1


def enumerated_decode(value, class_):
    assert isinstance(value, str)
    return class_(value)


def date_encode(value):
    if value.is_special:
        return str(value)
    else:
        return "{:04d}-{:02d}-{:02d}".format(value[0] + 1900, value[1], value[2])


def date_decode(value, class_):
    assert isinstance(value, str)
    return class_(value)


def time_encode(value):
    return str(value)


def time_decode(value, class_):
    assert isinstance(value, str)
    return class_(value)


def objectidentifier_encode(value):
    return str(value)


def objectidentifier_decode(value, class_):
    assert isinstance(value, str)
    return class_(value)


#
#   Atomic encoding and decoding
#


def atomic_encode(value) -> _Any:
    if isinstance(value, Null):
        literal = null_encode(value)
    elif isinstance(value, Boolean):
        literal = boolean_encode(value)
    elif isinstance(value, Unsigned):
        literal = unsigned_encode(value)
    elif isinstance(value, Integer):
        literal = integer_encode(value)
    elif isinstance(value, Real):
        literal = real_encode(value)
    elif isinstance(value, Double):
        literal = double_encode(value)
    elif isinstance(value, OctetString):
        literal = octetstring_encode(value)
    elif isinstance(value, CharacterString):
        literal = characterstring_encode(value)
    elif isinstance(value, BitString):
        literal = bitstring_encode(value)
    elif isinstance(value, Enumerated):
        literal = enumerated_encode(value)
    elif isinstance(value, Date):
        literal = date_encode(value)
    elif isinstance(value, Time):
        literal = time_encode(value)
    elif isinstance(value, ObjectIdentifier):
        literal = objectidentifier_encode(value)
    else:
        raise TypeError("atomic element expected: " + str(type(value)))

    return literal


def atomic_decode(literal, class_) -> Atomic:
    if issubclass(class_, Null):
        value = null_decode(literal, class_)
    elif issubclass(class_, Boolean):
        value = boolean_decode(literal, class_)
    elif issubclass(class_, Unsigned):
        value = unsigned_decode(literal, class_)
    elif issubclass(class_, Integer):
        value = integer_decode(literal, class_)
    elif issubclass(class_, Real):
        value = real_decode(literal, class_)
    elif issubclass(class_, Double):
        value = double_decode(literal, class_)
    elif issubclass(class_, OctetString):
        value = octetstring_decode(literal, class_)
    elif issubclass(class_, CharacterString):
        value = characterstring_decode(literal, class_)
    elif issubclass(class_, BitString):
        value = bitstring_decode(literal, class_)
    elif issubclass(class_, Enumerated):
        value = enumerated_decode(literal, class_)
    elif issubclass(class_, Date):
        value = date_decode(literal, class_)
    elif issubclass(class_, Time):
        value = time_decode(literal, class_)
    elif issubclass(class_, ObjectIdentifier):
        value = objectidentifier_decode(literal, class_)
    else:
        raise TypeError("not an atomic element")

    return value


#
#   Constructed Data
#


@bacpypes_debugging
def sequence_to_json(seq: Sequence) -> JSONDict:
    """Encode a sequence as a JSONDict."""
    if _debug:
        sequence_to_json._debug("sequence_to_json %r", seq)

    json = {}
    for attr, element in seq._elements.items():
        # ask the element to get the value
        getattr_fn = partial(seq.__getattribute__, attr)
        value = element.get_attribute(getter=getattr_fn)
        if _debug:
            sequence_to_json._debug(f"    - {attr}, {element}: {value}")
        if value is None:
            continue

        if isinstance(value, Atomic):
            json_value = atomic_encode(value)
        elif isinstance(value, Sequence):
            json_value = sequence_to_json(value)
        elif isinstance(value, ExtendedList):
            json_value = extendedlist_to_json_list(value)
        elif isinstance(value, Any):
            json_value = taglist_to_json_list(value.tagList)
        else:
            raise TypeError(value)

        json[attr_to_asn1(attr)] = json_value

    return json


@bacpypes_debugging
def json_to_sequence(json: JSONDict, seq_class: type) -> Sequence:
    """Decode a sequence from a graph."""
    if _debug:
        json_to_sequence._debug("json_to_sequence %r %r", json, seq_class)

    # create an instance of the class
    seq = seq_class()

    # look for the elements in order
    for attr, element in seq._elements.items():
        if _debug:
            json_to_sequence._debug("    - attr, element: %r, %r", attr, element)

        value = json.pop(attr_to_asn1(attr), None)
        if _debug:
            json_to_sequence._debug("    - value: %r", value)
        if value is None:
            continue

        if issubclass(element, Atomic):
            value = atomic_decode(value, element)
        elif issubclass(element, Sequence):
            value = json_to_sequence(value, element)
        elif issubclass(element, ExtendedList):
            value = json_list_to_extendedlist(value, element)
        elif issubclass(element, Any):
            value = json_list_to_taglist(value)
        else:
            raise TypeError(element)

        # ask the element to set the value
        getattr_fn = partial(seq.__getattribute__, attr)
        setattr_fn = partial(seq.__setattr__, attr)
        element.set_attribute(
            getter=getattr_fn,
            setter=setattr_fn,
            value=value,
        )

    # return the sequence
    return seq


#
#   ExtendedList
#


@bacpypes_debugging
def extendedlist_to_json_list(
    xlist: ExtendedList,
) -> _List[_Any]:
    """Encode an extended list as an array."""
    if _debug:
        extendedlist_to_json_list._debug("extendedlist_to_json_list %r", xlist)

    result = []
    for value in xlist:
        if isinstance(value, Atomic):
            value = atomic_encode(value)
        elif isinstance(value, Sequence):
            value = sequence_to_json(value)
        else:
            raise TypeError(value)

        result.append(value)

    return result


@bacpypes_debugging
def json_list_to_extendedlist(
    json_list: _List[_Any], xlist_class: type
) -> ExtendedList:
    """Decode an extended list from a graph."""
    if _debug:
        json_list_to_extendedlist._debug(
            "json_list_to_extendedlist %r %r", json_list, xlist_class
        )

    xlist = []
    xlist_class_subtype = xlist_class._subtype  # type: ignore[attr-defined]

    for value in json_list:
        if issubclass(xlist_class_subtype, Atomic):
            value = atomic_decode(value, xlist_class_subtype)
        elif issubclass(xlist_class_subtype, Sequence):
            value = json_to_sequence(value, xlist_class_subtype)
        else:
            raise TypeError(xlist_class_subtype)

        xlist.append(value)

    return xlist_class(xlist)


#
#   Any
#


@bacpypes_debugging
def taglist_to_json_list(tag_list: TagList) -> _List[Dict[str, _Any]]:
    """ """
    if _debug:
        taglist_to_json_list._debug("taglist_to_json_list %r", tag_list)

    json_list = []
    for tag in tag_list:
        if _debug:
            taglist_to_json_list._debug("     - tag: %r", tag)

        if tag.tag_class == TagClass.application:
            tag_name = tag._app_tag_name[tag.tag_number]
            if tag.tag_number == TagNumber.boolean:
                tag_dict = {tag_name: tag.tag_lvt}
            else:
                tag_dict = {tag_name: binascii.b2a_hex(tag.tag_data).decode()}

        elif tag.tag_class == TagClass.context:
            tag_dict = {
                "context": tag.tag_number,
                "data": binascii.b2a_hex(tag.tag_data).decode(),
            }

        if tag.tag_class == TagClass.opening:
            tag_dict = {"opening": tag.tag_number}

        elif tag.tag_class == TagClass.closing:
            tag_dict = {"closing": tag.tag_number}

        json_list.append(tag_dict)

    return json_list


@bacpypes_debugging
def json_list_to_taglist(json_list: _List[Dict[str, _Any]]) -> Any:
    """ """
    if _debug:
        json_list_to_taglist._debug("json_list_to_taglist %r", json_list)

    tag_list = TagList()
    for tag_dict in json_list:
        if _debug:
            json_list_to_taglist._debug("     - tag_dict: %r", tag_dict)

        if "opening" in tag_dict:
            tag = OpeningTag(tag_dict["opening"])

        elif "closing" in tag_dict:
            tag = ClosingTag(tag_dict["closing"])

        elif "context" in tag_dict:
            tag = ContextTag(tag_dict["context"], binascii.a2b_hex(tag_dict["data"]))

        else:
            tag_name, tag_data = list(tag_dict.items())[0]
            tag_number = tag._app_tag_name.index(tag_name)

            if tag_number == TagNumber.boolean:
                tag = Tag(
                    TagClass.application,
                    TagNumber.boolean,
                    tag_data,
                    b"",
                )
            else:
                tag = ApplicationTag(tag_number, binascii.a2b_hex(tag_data))

        tag_list.append(tag)

    return tag_list


#
#   APDU
#


@bacpypes_debugging
def apdu_to_json(apdu: APDU) -> JSONDict:
    """ """
    if _debug:
        apdu_to_json._debug("apdu_to_json %r", apdu)

    json_blob: JSONDict
    if isinstance(apdu, APCISequence):
        json_blob = sequence_to_json(apdu)
    else:
        json_blob = {}

    for attr in APCI._debug_contents:
        attr_value = getattr(apdu, attr, None)
        if attr_value is not None:
            json_blob[attr] = attr_value

    for attr in PCI._debug_contents:
        attr_value = getattr(apdu, attr, None)
        if attr_value is not None:
            if attr in ("pduSource", "pduDestination"):
                attr_value = str(attr_value)
            json_blob[attr] = attr_value

    return json_blob


@bacpypes_debugging
def json_to_apdu(json_blob: JSONDict) -> APDU:
    """ """
    if _debug:
        json_to_apdu._debug("json_to_apdu %r", json_blob)

    # extract the type and service to find the appropriate class
    apdu_type = json_blob.pop("apduType", None)
    apdu_service = json_blob.pop("apduService", None)
    if not apdu_type:
        raise DecodingError("apduType expected")

    try:
        if apdu_type == ConfirmedRequestPDU.pduType:
            apdu_class = confirmed_request_types[apdu_service]
        elif apdu_type == UnconfirmedRequestPDU.pduType:
            apdu_class = unconfirmed_request_types[apdu_service]
        elif apdu_type == SimpleAckPDU.pduType:
            apdu_class = SimpleAckPDU
        elif apdu_type == ComplexAckPDU.pduType:
            apdu_class = complex_ack_types[apdu_service]
        elif apdu_type == SegmentAckPDU.pduType:
            apdu_class = SegmentAckPDU
        elif apdu_type == ErrorPDU.pduType:
            apdu_class = error_types[apdu_service]
        elif apdu_type == RejectPDU.pduType:
            apdu_class = RejectPDU
        elif apdu_type == AbortPDU.pduType:
            apdu_class = AbortPDU
        else:
            raise TypeError(f"invalid APDU type: {apdu_type}")
    except KeyError:
        raise RuntimeError(f"unrecognized service choice: {apdu_service}")

    apdu = apdu_class()

    if issubclass(apdu_class, APCISequence):
        apdu = json_to_sequence(json_blob, apdu_class)
    else:
        apdu = apdu_class()

    for attr in PCI._debug_contents:
        attr_value = json_blob.pop(attr, None)
        if attr_value is not None:
            if attr in ("pduSource", "pduDestination"):
                attr_value = Address(attr_value)
            setattr(apdu, attr, attr_value)

    for attr in APCI._debug_contents:
        attr_value = json_blob.pop(attr, None)
        if attr_value is not None:
            setattr(apdu, attr, attr_value)

    if json_blob:
        if _debug:
            json_to_apdu._debug("     - extra: %r", json_blob)
        raise DecodingError(f"extra content: {json_blob}")

    return apdu
