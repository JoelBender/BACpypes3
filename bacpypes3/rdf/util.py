"""
Utility functions
"""

import re
import base64
from functools import partial

from typing import Optional

from rdflib import Graph, Literal, BNode, URIRef  # type: ignore[import]
from rdflib.namespace import Namespace, RDF, XSD  # type: ignore[import]

from ..debugging import bacpypes_debugging, ModuleLogger

from ..primitivedata import (
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
    AnyAtomic,
    Sequence,  # covers both Sequence and Choice
    ExtendedList,  # covers SequenceOf, ArrayOf, and ListOf
)
from ..basetypes import DateTime, AnyAtomicExtended

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# note: defined in both core.py and util.py
BACnetNS = Namespace("http://data.ashrae.org/bacnet/2016#")

# enumeration names are analog-value rather that analogValue
_unupper_re = re.compile("[A-Z]{2,}(?:(?=[A-Z][a-z])|$)")
_wordsplit_re = re.compile(r"([a-z0-9])([A-Z])")


def attr_to_predicate(k: str):
    """
    Given an attribute name return its URI.
    """
    # translate DHCPSnork to DhcpSnork, isUTC to isUtc
    k = _unupper_re.sub(lambda m: m.group(0)[0] + m.group(0)[1:].lower(), k)

    # translate lowerCamel to lower-camel
    k = _wordsplit_re.sub(lambda m: m.group(1) + "-" + m.group(2).lower(), k)

    # more exceptions
    k = k.replace("-ipnat-", "-ip-nat-")
    k = k.replace("-ipudp-", "-ip-udp-")

    return BACnetNS[k]


#
#   Primitive Data
#

_bitstring_as_bits = 0
_bitstring_as_str = 0
_bitstring_as_list = 1

_enumerated_as_str = 0
_enumerated_as_uri = 1
_enumerated_as_datatype = 0

_octetstring_as_base64Binary = 0
_octetstring_as_hexBinary = 1


def null_encode(graph: Graph, value):
    return BACnetNS.Null


def null_decode(graph: Graph, value):
    assert value == BACnetNS.Null
    return Null(())


def boolean_encode(graph: Graph, value):
    return Literal(bool(value))


def boolean_decode(graph: Graph, value):
    assert isinstance(value, Literal) and (value.datatype == XSD.boolean)
    return Boolean(value.value)


def unsigned_encode(graph: Graph, value):
    return Literal(value, datatype=XSD.nonNegativeInteger)


def unsigned_decode(graph: Graph, value):
    assert isinstance(value, Literal) and (value.datatype == XSD.nonNegativeInteger)
    return Unsigned(value.value)


def integer_encode(graph: Graph, value):
    return Literal(value, datatype=XSD.integer)


def integer_decode(graph: Graph, value):
    assert isinstance(value, Literal) and (value.datatype == XSD.integer)
    return Integer(value.value)


def real_encode(graph: Graph, value):
    return Literal(value, datatype=XSD.float)


def real_decode(graph: Graph, value):
    assert isinstance(value, Literal) and (value.datatype == XSD.float)
    return Real(value.value)


def double_encode(graph: Graph, value):
    return Literal(value, datatype=XSD.double)


def double_decode(graph: Graph, value):
    assert isinstance(value, Literal) and (value.datatype == XSD.double)
    return Double(value.value)


def octetstring_encode(graph: Graph, value):
    if _octetstring_as_base64Binary:
        base64_string = base64.b64encode(value).decode()
        return Literal(base64_string, datatype=XSD.base64Binary)

    if _octetstring_as_hexBinary:
        hex_string = value.hex()
        return Literal(hex_string, datatype=XSD.hexBinary)

    raise NotImplementedError("octetstring_encode")


def octetstring_decode(graph: Graph, value):
    if _octetstring_as_base64Binary:
        assert isinstance(value, Literal) and (value.datatype == XSD.base64Binary)
        return OctetString(value.value)

    if _octetstring_as_hexBinary:
        assert isinstance(value, Literal) and (value.datatype == XSD.hexBinary)
        return OctetString(value.value)

    raise NotImplementedError("octetstring_decode")


def characterstring_encode(graph: Graph, value):
    return Literal(value)


def characterstring_decode(graph: Graph, value):
    assert isinstance(value, Literal) and (value.datatype is None)
    return CharacterString(value.value)


def bitstring_encode(graph: Graph, value):
    if _bitstring_as_bits:
        bit_string = "".join(str(bit) for bit in value)
        return Literal(bit_string, datatype=BACnetNS.BitString)

    if _bitstring_as_str:
        return Literal(str(value))

    if _bitstring_as_list:
        bit_names = {v: k for k, v in value._bitstring_names.items()}

        list_head = list_tail = None
        for bit_number, bit in enumerate(value):
            if not bit:
                continue

            if bit_number in bit_names:
                literal = URIRef(
                    BACnetNS[value.__class__.__name__ + "." + bit_names[bit_number]]
                )
            else:
                literal = Literal(bit_number)

            # create a blank node referencing the thing
            list_node = BNode()
            graph.add((list_node, RDF.first, literal))
            if not list_head:
                list_head = list_node
            else:
                graph.add((list_tail, RDF.rest, list_node))
            list_tail = list_node

        # end of the list
        if list_head:
            graph.add((list_tail, RDF.rest, RDF.nil))
        else:
            list_head = RDF.nil

        return list_head

    raise NotImplementedError("bitstring_encode")


def bitstring_decode(graph: Graph, value, class_):
    if _bitstring_as_bits:
        assert isinstance(value, Literal) and (value.datatype == BACnetNS.BitString)
        bit_string = [int(c) for c in str(value) if c in ("0", "1")]
        return class_(bit_string)

    if _bitstring_as_str:
        return class_(str(value))

    if _bitstring_as_list:
        bits_set = set()

        list_node = value
        while list_node != RDF.nil:
            node_value = graph.value(subject=list_node, predicate=RDF.first)

            if isinstance(node_value, int):
                bits_set.add(node_value)
            elif isinstance(node_value, URIRef):
                uri_value = str(node_value).replace(str(BACnetNS), "").split(".", 1)
                assert uri_value[0] == class_.__name__

                bits_set.add(class_._bitstring_names[uri_value[1]])
            elif isinstance(node_value, str):
                bits_set.add(class_._bitstring_names[str(node_value)])
            else:
                raise TypeError(f"named bit: {node_value!r}")

            list_node = graph.value(subject=list_node, predicate=RDF.rest)

        bits_list = []
        if bits_set:
            for bit_number in range(max(max(bits_set) + 1, class_._bitstring_length)):
                bits_list.append(1 if bit_number in bits_set else 0)

        return class_(bits_list)

    raise NotImplementedError("bitstring_decode")


def enumerated_encode(graph: Graph, value):
    if _enumerated_as_str:
        return Literal(value.asn1)
    if _enumerated_as_datatype:
        return Literal(value.asn1, datatype=BACnetNS[value.__class__.__name__])
    if _enumerated_as_uri:
        return URIRef(BACnetNS[value.__class__.__name__ + "." + value.asn1])

    raise NotImplementedError("enumerated_encode")


def enumerated_decode(graph: Graph, value, class_):
    if _enumerated_as_str:
        assert isinstance(value, Literal)
        return class_(str(value))

    if _enumerated_as_datatype:
        assert isinstance(value, Literal)
        assert value.datatype == BACnetNS[class_.__name__]
        return class_(str(value))

    if _enumerated_as_uri:
        assert isinstance(value, URIRef)

        uri_value = str(value).replace(str(BACnetNS), "").split(".", 1)
        assert uri_value[0] == class_.__name__

        return class_(uri_value[1])

    raise NotImplementedError("enumeraeted_decode")


def date_encode(graph: Graph, value):
    if value.is_special:
        return Literal(str(value), datatype=BACnetNS.Date)
    else:
        date_string = "{:04d}-{:02d}-{:02d}".format(value[0] + 1900, value[1], value[2])
        return Literal(date_string, datatype=XSD.date, normalize=False)


def date_decode(graph: Graph, value):
    assert isinstance(value, Literal)
    if value.datatype == BACnetNS.Date:
        return Date(str(value))
    elif value.datatype == XSD.date:
        return Date(value.value)
    else:
        raise TypeError(value.datatype)


def time_encode(graph: Graph, value):
    time_string = str(value)
    if value.is_special:
        return Literal(time_string, datatype=BACnetNS.Time)
    else:
        return Literal(time_string, datatype=XSD.time, normalize=False)


def time_decode(graph: Graph, value):
    assert isinstance(value, Literal)
    if value.datatype == BACnetNS.Time:
        return Time(str(value))
    elif value.datatype == XSD.time:
        return Time(value.value)
    else:
        raise TypeError(value.datatype)


def objectidentifier_encode(graph: Graph, value):
    obj_type, obj_instance = value
    objectidentifier_string = "{},{}".format(obj_type, obj_instance)
    # alternate datatype=BACnetNS.ObjectIdentifier
    return Literal(objectidentifier_string)


def objectidentifier_decode(graph: Graph, value):
    # alternate (value.datatype == BACnetNS.ObjectIdentifier)
    assert isinstance(value, Literal) and (value.datatype is None)
    return ObjectIdentifier(str(value))


#
#
#


def atomic_encode(graph: Graph, value) -> Literal:
    if isinstance(value, Null):
        literal = null_encode(graph, value)
    elif isinstance(value, Boolean):
        literal = boolean_encode(graph, value)
    elif isinstance(value, Unsigned):
        literal = unsigned_encode(graph, value)
    elif isinstance(value, Integer):
        literal = integer_encode(graph, value)
    elif isinstance(value, Real):
        literal = real_encode(graph, value)
    elif isinstance(value, Double):
        literal = double_encode(graph, value)
    elif isinstance(value, OctetString):
        literal = octetstring_encode(graph, value)
    elif isinstance(value, CharacterString):
        literal = characterstring_encode(graph, value)
    elif isinstance(value, BitString):
        literal = bitstring_encode(graph, value)
    elif isinstance(value, Enumerated):
        literal = enumerated_encode(graph, value)
    elif isinstance(value, Date):
        literal = date_encode(graph, value)
    elif isinstance(value, Time):
        literal = time_encode(graph, value)
    elif isinstance(value, ObjectIdentifier):
        literal = objectidentifier_encode(graph, value)
    else:
        raise TypeError("atomic element expected: " + str(type(value)))

    return literal


def atomic_decode(graph: Graph, literal, class_) -> Atomic:
    if issubclass(class_, Null):
        value = null_decode(graph, literal)
    elif issubclass(class_, Boolean):
        value = boolean_decode(graph, literal)
    elif issubclass(class_, Unsigned):
        value = unsigned_decode(graph, literal)
    elif issubclass(class_, Integer):
        value = integer_decode(graph, literal)
    elif issubclass(class_, Real):
        value = real_decode(graph, literal)
    elif issubclass(class_, Double):
        value = double_decode(graph, literal)
    elif issubclass(class_, OctetString):
        value = octetstring_decode(graph, literal)
    elif issubclass(class_, CharacterString):
        value = characterstring_decode(graph, literal)
    elif issubclass(class_, BitString):
        value = bitstring_decode(graph, literal, class_)
    elif issubclass(class_, Enumerated):
        value = enumerated_decode(graph, literal, class_)
    elif issubclass(class_, Date):
        value = date_decode(graph, literal)
    elif issubclass(class_, Time):
        value = time_decode(graph, literal)
    elif issubclass(class_, ObjectIdentifier):
        value = objectidentifier_decode(graph, literal)
    else:
        raise TypeError("not an atomic element")

    return value


#
#   Constructed Data
#


@bacpypes_debugging
def sequence_to_graph(
    seq: Sequence, node: URIRef, graph: Optional[Graph] = None
) -> Graph:
    """Encode a sequence as a graph."""
    if _debug:
        sequence_to_graph._debug("sequence_to_graph %r %r %r", seq, node, graph)

    # make a graph if one wasn't provided
    if graph is None:
        graph = Graph()
        graph.bind("bacnet", BACnetNS)

    for attr, element in seq._elements.items():
        # ask the element to get the value
        getattr_fn = partial(seq.__getattribute__, attr)
        value = element.get_attribute(getter=getattr_fn)
        if _debug:
            sequence_to_graph._debug(f"    - {attr}, {element}: {value}")
        if value is None:
            continue

        if isinstance(value, Atomic):
            literal = atomic_encode(graph, value)
        elif isinstance(value, Sequence):
            literal = BNode()
            sequence_to_graph(value, literal, graph)
        elif isinstance(value, ExtendedList):
            extendedlist_to_graph(value, node, attr_to_predicate(attr), graph)
            continue
        elif isinstance(value, (AnyAtomic, AnyAtomicExtended)):
            value = value.get_value()
            if isinstance(value, Atomic):
                literal = atomic_encode(graph, value)
            elif isinstance(value, DateTime):
                literal = BNode()
                sequence_to_graph(value, literal, graph)
        else:
            raise TypeError(value)

        graph.add((node, attr_to_predicate(attr), literal))

    return graph


@bacpypes_debugging
def graph_to_sequence(graph: Graph, node: URIRef, seq_class: type) -> Sequence:
    """Decode a sequence from a graph."""
    if _debug:
        graph_to_sequence._debug("graph_to_sequence %r %r %r", graph, node, seq_class)

    # create an instance of the class
    seq = seq_class()

    # look for the elements in order
    for attr, element in seq._elements.items():
        if _debug:
            Sequence._debug("    - attr, element: %r, %r", attr, element)

        literal = graph.value(subject=node, predicate=attr_to_predicate(attr))
        if _debug:
            Sequence._debug("    - literal: %r", literal)
        if literal is None:
            continue

        if issubclass(element, Atomic):
            value = atomic_decode(graph, literal, element)
        elif issubclass(element, Sequence):
            value = graph_to_sequence(graph, literal, element)
        elif issubclass(element, ExtendedList):
            value = graph_to_extendedlist(graph, node, attr_to_predicate(attr), element)
        elif issubclass(element, (AnyAtomic, AnyAtomicExtended)):
            if literal == BACnetNS.Null:
                value = Null(())

            elif isinstance(literal, (BNode, URIRef)):
                date_literal = graph.value(subject=literal, predicate=BACnetNS["date"])
                time_literal = graph.value(subject=literal, predicate=BACnetNS["time"])
                if (date_literal is not None) and (time_literal is not None):
                    value = DateTime(
                        date=date_decode(graph, date_literal),
                        time=time_decode(graph, time_literal),
                    )
                else:
                    raise ValueError("DateTime expected")

            elif isinstance(literal, Literal):
                if literal.datatype == XSD.boolean:
                    value = boolean_decode(graph, literal)
                elif literal.datatype == XSD.nonNegativeInteger:
                    value = unsigned_decode(graph, literal)
                elif literal.datatype == XSD.integer:
                    value = integer_decode(graph, literal)
                elif literal.datatype == XSD.float:
                    value = real_decode(graph, literal)
                elif literal.datatype == XSD.double:
                    value = double_decode(graph, literal)
                elif literal.datatype == XSD.base64Binary:
                    value = octetstring_decode(graph, literal)
                elif literal.datatype == XSD.hexBinary:
                    value = octetstring_decode(graph, literal)
                elif literal.datatype is None:
                    value = characterstring_decode(graph, literal)
                elif literal.datatype == BACnetNS.BitString:
                    value = bitstring_decode(graph, literal)
                elif literal.datatype in (BACnetNS.Date, XSD.date):
                    value = date_decode(graph, literal)
                elif literal.datatype in (BACnetNS.Time, XSD.time):
                    value = time_decode(graph, literal)
                elif literal.datatype == BACnetNS.ObjectIdentifier:
                    value = objectidentifier_decode(graph, literal)
                else:
                    raise ValueError(literal.datatype)
            else:
                raise ValueError(literal)
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
def extendedlist_to_graph(
    xlist: ExtendedList,
    subject: URIRef,
    predicate: URIRef,
    graph: Optional[Graph] = None,
) -> Graph:
    """Encode an extended list as a graph."""
    if _debug:
        extendedlist_to_graph._debug(
            "extendedlist_to_graph %r %r %r %r", xlist, subject, predicate, graph
        )

    # make a graph if one wasn't provided
    if graph is None:
        graph = Graph()
        graph.bind("bacnet", BACnetNS)

    for value in xlist:
        if isinstance(value, Atomic):
            literal = atomic_encode(graph, value)
        elif isinstance(value, Sequence):
            literal = BNode()
            sequence_to_graph(value, literal, graph)
        else:
            raise TypeError(value)

        # create a blank node referencing the thing
        list_node = BNode()
        graph.add((list_node, RDF.first, literal))

        # chain along this list node
        graph.add((subject, predicate, list_node))
        subject = list_node
        predicate = RDF.rest

    # end of the list
    graph.add((subject, predicate, RDF.nil))

    return graph


@bacpypes_debugging
def graph_to_extendedlist(
    graph: Graph, subject: URIRef, predicate: URIRef, xlist_class: type
) -> ExtendedList:
    """Decode an extended list from a graph."""
    if _debug:
        graph_to_extendedlist._debug(
            "graph_to_extendedlist %r %r %r %r", graph, subject, predicate, xlist_class
        )

    list_node = graph.value(subject=subject, predicate=predicate)
    if _debug:
        Sequence._debug("    - list_node: %r", list_node)
    if list_node is None:
        return None

    xlist = []
    xlist_class_subtype = xlist_class._subtype  # type: ignore[attr-defined]

    while list_node != RDF.nil:
        node_value = graph.value(subject=list_node, predicate=RDF.first)

        if issubclass(xlist_class_subtype, Atomic):
            value = atomic_decode(graph, node_value, xlist_class_subtype)
        elif issubclass(xlist_class_subtype, Sequence):
            value = graph_to_sequence(graph, node_value, xlist_class_subtype)
        else:
            raise TypeError(xlist_class_subtype)

        xlist.append(value)
        list_node = graph.value(subject=list_node, predicate=RDF.rest)

    return xlist_class(xlist)
