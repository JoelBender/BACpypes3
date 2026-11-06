"""
Utility functions
"""

import re
import base64
from functools import partial

from typing import Any, Optional, Union

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
    Tag,
    TagClass,
)
from ..constructeddata import (
    Any as AnyElement,
    AnyAtomic,
    Sequence,  # covers both Sequence and Choice
    ExtendedList,  # covers SequenceOf, ArrayOf, and ListOf
)
from ..basetypes import DateTime, AnyAtomicExtended

# some debugging
_debug = 0
_log = ModuleLogger(globals())


# note: defined in both core.py and util.py
BACNET = Namespace("http://data.ashrae.org/bacnet/")

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

    return BACNET[k]


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
    return BACNET.Null


def null_decode(graph: Graph, value):
    assert value == BACNET.Null
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
        return Literal(bit_string, datatype=BACNET.bitString)

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
                    BACNET[value.__class__.__name__ + "." + bit_names[bit_number]]
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
        assert isinstance(value, Literal) and (value.datatype == BACNET.bitString)
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
                uri_value = str(node_value).replace(str(BACNET), "").split(".", 1)
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
        return Literal(value.asn1, datatype=BACNET[value.__class__.__name__])
    if _enumerated_as_uri:
        return URIRef(BACNET[value.__class__.__name__ + "." + value.asn1])

    raise NotImplementedError("enumerated_encode")


def enumerated_decode(graph: Graph, value, class_):
    if _enumerated_as_str:
        assert isinstance(value, Literal)
        return class_(str(value))

    if _enumerated_as_datatype:
        assert isinstance(value, Literal)
        assert value.datatype == BACNET[class_.__name__]
        return class_(str(value))

    if _enumerated_as_uri:
        assert isinstance(value, URIRef)

        uri_value = str(value).replace(str(BACNET), "").split(".", 1)
        assert uri_value[0] == class_.__name__

        return class_(uri_value[1])

    raise NotImplementedError("enumeraeted_decode")


def date_encode(graph: Graph, value):
    if value.is_special:
        return Literal(str(value), datatype=BACNET.datePattern)
    else:
        return Literal(value.date)


def date_decode(graph: Graph, value):
    assert isinstance(value, Literal)
    if value.datatype == BACNET.datePattern:
        return Date(str(value))
    elif value.datatype == XSD.date:
        return Date(value.value)
    else:
        raise TypeError(value.datatype)


def time_encode(graph: Graph, value):
    if value.is_special:
        return Literal(str(value), datatype=BACNET.timePattern)
    else:
        return Literal(value.time)  # normalize=False?


def time_decode(graph: Graph, value):
    assert isinstance(value, Literal)
    if value.datatype == BACNET.timePattern:
        return Time(str(value))
    elif value.datatype == XSD.time:
        return Time(value.value)
    else:
        raise TypeError(value.datatype)


def objectidentifier_encode(graph: Graph, value):
    obj_type, obj_instance = value
    objectidentifier_string = "{},{}".format(obj_type, obj_instance)
    return Literal(objectidentifier_string, datatype=BACNET.objectIdentifier)


def objectidentifier_decode(graph: Graph, value):
    assert isinstance(value, Literal) and (value.datatype is BACNET.objectIdentifier)
    return ObjectIdentifier(str(value))


def datetime_encode(graph: Graph, value):
    if value.is_special:
        return Literal(str(value), datatype=BACNET.dateTimePattern)
    else:
        return Literal(value.datetime)  # normalize=False?


def datetime_decode(graph: Graph, value):
    assert isinstance(value, Literal)
    if value.datatype == BACNET.dateTimePattern:
        return DateTime(str(value))
    elif value.datatype == XSD.dateTime:
        return DateTime(value.value)
    else:
        raise TypeError(value.datatype)


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
    elif isinstance(value, DateTime):
        literal = datetime_encode(graph, value)
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
    elif issubclass(class_, DateTime):
        value = datetime_decode(graph, literal)
    else:
        raise TypeError("not an atomic element")

    return value


#
#   Any
#


def any_encode(graph: Graph, value: AnyElement) -> Union[Literal, URIRef, BNode]:
    """Encode an Any, AnyAtomic or AnyAtomicExtended.  When the content is a
    single application tagged value (or a DateTime) it is encoded like any
    other value of that type, so a schedule-default of 72.0 is the same
    literal as a present-value of 72.0.  Anything else (context tagged or
    constructed content whose type is not known without the property
    context) becomes a blank node whose bacnet:any is an RDF list with one
    node per tag, following Any.dict_contents() (the analysis module JSON):

        [ bacnet:any ( [ bacnet:real "1.0"^^xsd:float ] [ bacnet:open 3 ]
                       [ bacnet:context 0 ; bacnet:data "05"^^xsd:hexBinary ]
                       [ bacnet:close 3 ] ) ]

    Context tags keep their data (hex) because its type is not known."""
    if value.tagList is None:
        return BACNET.Null

    if isinstance(value, (AnyAtomic, AnyAtomicExtended)):
        try:
            return value_encode(graph, value.get_value())
        except TypeError:
            pass

    # an Any inside a sequence carries its context tag, look inside it
    tags = list(value.tagList)
    if (
        (len(tags) >= 2)
        and (tags[0].tag_class == TagClass.opening)
        and (tags[-1].tag_class == TagClass.closing)
        and (tags[0].tag_number == tags[-1].tag_number)
    ):
        tags = tags[1:-1]
    if (len(tags) == 1) and (tags[0].tag_class == TagClass.application):
        return atomic_encode(graph, tags[0].app_to_object())

    node = BNode()
    head = RDF.nil
    for tag in reversed(tags):
        list_node = BNode()
        graph.add((list_node, RDF.first, tag_encode(graph, tag)))
        graph.add((list_node, RDF.rest, head))
        head = list_node
    graph.add((node, BACNET["any"], head))
    return node


def tag_encode(graph: Graph, tag: Tag) -> BNode:
    """Encode one tag of an Any the way Tag.dict_contents() describes it."""
    node = BNode()
    if tag.tag_class == TagClass.application:
        graph.add(
            (
                node,
                attr_to_predicate(Tag._app_tag_name[tag.tag_number]),
                atomic_encode(graph, tag.app_to_object()),
            )
        )
    elif tag.tag_class == TagClass.opening:
        graph.add((node, BACNET["open"], Literal(tag.tag_number)))
    elif tag.tag_class == TagClass.closing:
        graph.add((node, BACNET["close"], Literal(tag.tag_number)))
    elif tag.tag_class == TagClass.context:
        graph.add((node, BACNET["context"], Literal(tag.tag_number)))
        graph.add(
            (
                node,
                BACNET["data"],
                Literal(bytes(tag.tag_data).hex(), datatype=XSD.hexBinary),
            )
        )
    else:
        raise TypeError(f"unexpected tag class: {tag.tag_class}")
    return node


def value_encode(graph: Graph, value: Any) -> Union[Literal, URIRef, BNode]:
    """Encode any BACnet value and return the node that represents it, adding
    triples to the graph for blank nodes and lists as needed."""
    if isinstance(value, Atomic):
        return atomic_encode(graph, value)
    if isinstance(value, DateTime):
        # DateTime is a Sequence, check it first
        return datetime_encode(graph, value)
    if isinstance(value, Sequence):
        node = BNode()
        sequence_to_graph(value, node, graph)
        return node
    if isinstance(value, ExtendedList):
        return extendedlist_to_node(value, graph)
    if isinstance(value, AnyElement):
        # covers AnyAtomic and AnyAtomicExtended
        return any_encode(graph, value)

    raise TypeError(f"unable to encode {type(value).__name__}")


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
        graph.bind("bacnet", BACNET)

    for attr, element in seq._elements.items():
        # ask the element to get the value
        getattr_fn = partial(seq.__getattribute__, attr)
        value = element.get_attribute(getter=getattr_fn)
        if _debug:
            sequence_to_graph._debug(f"    - {attr}, {element}: {value}")
        if value is None:
            continue

        graph.add((node, attr_to_predicate(attr), value_encode(graph, value)))

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
        elif issubclass(element, DateTime):
            value = datetime_decode(graph, literal)
        elif issubclass(element, Sequence):
            value = graph_to_sequence(graph, literal, element)
        elif issubclass(element, ExtendedList):
            value = graph_to_extendedlist(graph, node, attr_to_predicate(attr), element)
        elif issubclass(element, (AnyAtomic, AnyAtomicExtended)):
            if literal == BACNET.Null:
                value = Null(())
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
                elif literal.datatype == BACNET.bitString:
                    value = bitstring_decode(graph, literal)
                elif literal.datatype in (BACNET.datePattern, XSD.date):
                    value = date_decode(graph, literal)
                elif literal.datatype in (BACNET.timePattern, XSD.time):
                    value = time_decode(graph, literal)
                elif literal.datatype == BACNET.objectIdentifier:
                    value = objectidentifier_decode(graph, literal)
                elif literal.datatype in (BACNET.dateTimePattern, XSD.dateTime):
                    value = datetime_decode(graph, literal)
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
        graph.bind("bacnet", BACNET)

    for value in xlist:
        # create a blank node referencing the thing
        list_node = BNode()
        graph.add((list_node, RDF.first, value_encode(graph, value)))

        # chain along this list node
        graph.add((subject, predicate, list_node))
        subject = list_node
        predicate = RDF.rest

    # end of the list
    graph.add((subject, predicate, RDF.nil))

    return graph


def extendedlist_to_node(xlist: ExtendedList, graph: Graph) -> Union[URIRef, BNode]:
    """Encode an extended list as an RDF list and return its head, which is
    rdf:nil for an empty list."""
    head = BNode()
    extendedlist_to_graph(xlist, head, RDF.rest, graph)
    first = graph.value(head, RDF.rest)
    graph.remove((head, RDF.rest, first))
    return first


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
