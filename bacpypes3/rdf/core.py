"""
Core
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from rdflib import Graph, Literal, BNode, URIRef  # type: ignore[import]
from rdflib.namespace import Namespace, RDF, RDFS, XSD  # type: ignore[import]
from rdflib.plugins.sparql import prepareQuery  # type: ignore[import]

from ..debugging import bacpypes_debugging, ModuleLogger, btox

from ..pdu import Address
from ..primitivedata import (
    Atomic,
    ObjectIdentifier,
)
from ..basetypes import PropertyIdentifier
from ..constructeddata import Sequence

from .util import atomic_encode, attr_to_predicate, sequence_to_graph

# some debugging
_debug = 0
_log = ModuleLogger(globals())


BACnetNS = Namespace("http://data.ashrae.org/bacnet/2016#")
BACnetURI = Namespace("bacnet:")

#
#   Node Identifiers
#


def device_node(
    device_identifier: ObjectIdentifier,
) -> URIRef:
    """Given a device identifer return a URI reference for the device, the
    default function returns a value from Annex Q.8."""
    return BACnetURI["//" + str(device_identifier[1])]


def object_node(
    device_iri: URIRef,
    object_identifier: ObjectIdentifier,
) -> URIRef:
    """Given a device IRI for context and an object identifier,
    return a URI reference for the object."""
    return device_iri + "/" + str(object_identifier)


def property_node(
    object_iri: URIRef,
    property_identifier: PropertyIdentifier,
) -> URIRef:
    """Given an object IRI for context and a property identifier, return a URI
    reference for the property."""
    return object_iri + "/" + str(property_identifier)


def blank_node() -> URIRef:
    """Return a blank node."""
    return BNode()


_device_node: Callable[..., URIRef] = device_node
_object_node: Callable[..., URIRef] = object_node
_blank_node: Callable[..., URIRef] = blank_node


def set_identifier_functions(
    *,
    device_node_fn: Callable[..., URIRef] = device_node,
    object_node_fn: Callable[..., URIRef] = object_node,
    blank_node_fn: Callable[..., URIRef] = blank_node,
):
    """This function allows the application using the library to provide
    its own functions for contsructing URI node identifiers for
    devices, objects and blank nodes.
    """
    global _device_node, _object_node, _blank_node

    _device_node = device_node_fn
    _object_node = object_node_fn
    _blank_node = blank_node_fn


#
#   Common prepared queries
#


def bacnet_query(query: str) -> Any:
    """Prepare a SPARQL query with the BACnet namespace prefix included.
    The prepared query is provided to the `BACnetGraph.query()` method
    along with initial variable bindings if they have been provided.
    """
    return prepareQuery(query, initNs={"bacnet": BACnetNS})


find_device_by_address = bacnet_query(
    """
    select ?s where { ?s bacnet:hasAddress [
        bacnet::network-number ?net ;
        bacnet:mac-address ?addr
        ] }
    """
)
find_device_by_instance = bacnet_query(
    "select ?s where { ?s bacnet:deviceInstance ?device_instance .}"
)
find_object_by_type = bacnet_query(
    "select ?s where { ?s bacnet:object-type ?objtype .}"
)


#
#   BACnetGraph
#


@bacpypes_debugging
class BACnetGraph:
    """
    Creates a graph context where BACnet content can be found.
    """

    _debug: Callable[..., None]

    def __init__(self, graph: Graph) -> None:
        self.graph = graph

        # bind the BACnet namespace
        self.graph.namespace_manager.bind("bacnet", URIRef(BACnetNS))

    def bind_namespace(self, prefix: str, uri: str) -> Namespace:
        """
        Create a Namespace and bind a prefix to it in the graph.
        """
        namespace = Namespace(uri)
        self.graph.namespace_manager.bind(prefix, URIRef(uri))
        return namespace

    def query(self, query: Any, **kwargs: Any) -> Any:
        """Run a prepared SPARQL query in the graph with the initial bindings
        and return the results.
        """
        # translate the query arguments to make it easy
        init_bindings = {}
        for k, v in kwargs.items():
            if isinstance(v, (URIRef, Literal)):
                pass
            elif isinstance(v, Atomic):
                v = atomic_encode(self.graph, v)
            elif isinstance(v, (int, float, str)):
                v = Literal(v)
            else:
                raise TypeError(f"keyword {k}: {type(v)}")

            init_bindings[k] = v

        # run the query
        return self.graph.query(query, initBindings=init_bindings)

    def create_device(
        self,
        device_address: Optional[Address],
        device_identifier: Optional[ObjectIdentifier],
    ) -> DeviceGraph:
        """Given a device network address or a device identifier (or both)
        create and return a DeviceGraph for the device.
        """
        device_iri = _device_node(device_identifier)
        self.graph.add((device_iri, RDF.type, BACnetNS.BACnetDevice))

        if device_address is not None:
            device_address_iri = _blank_node()
            self.graph.add((device_iri, BACnetNS.hasAddress, device_address_iri))

            # encode the network portion, local stations are network 0
            self.graph.add(
                (device_address_iri, RDFS.label, Literal(str(device_address)))
            )

            if device_address.addrNet is None:
                device_address_net = Literal(0)
            else:
                device_address_net = Literal(device_address.addrNet)

            # encode the MAC address, hex string?
            device_address_mac = Literal(
                btox(device_address.addrAddr), datatype=XSD.hexBinary
            )

            device_address_proxy = ObjectProxy(self, device_address_iri)
            device_address_proxy.networkNumber = device_address_net
            device_address_proxy.macAddress = device_address_mac

        if device_identifier is not None:
            self.graph.add(
                (device_iri, BACnetNS.deviceInstance, Literal(device_identifier[1]))
            )

        return DeviceGraph(self, device_iri)

    def find_device(
        self,
        device_address: Optional[Address] = None,
        device_identifier: Optional[ObjectIdentifier] = None,
    ) -> Optional[DeviceGraph]:
        """Given a device network address or a device identifier (or both)
        find the existing DeviceGraph for the device, or return None if
        the device isn't defined.
        """
        return None

    def delete_device(
        self,
        device_address: Optional[Address] = None,
        device_identifier: Optional[ObjectIdentifier] = None,
    ) -> None:
        """Given a device network address or a device identifier (or both)
        find the existing DeviceGraph for the device and delete all of its
        associated nodes.
        """
        pass


#
#   DeviceGraph
#


@bacpypes_debugging
class DeviceGraph:
    """
    Creates a graph context where BACnet content for a specific device
    can be found.
    """

    _debug: Callable[..., None]

    def __init__(self, graph: BACnetGraph, device_iri: URIRef) -> None:
        self.graph = graph
        self.device_iri = device_iri

    def create_object(self, object_identifier: ObjectIdentifier) -> ObjectProxy:
        """Given an object identifier return an ObjectProxy for the object."""
        object_iri = _object_node(self.device_iri, object_identifier)

        object_proxy = ObjectProxy(self.graph, object_iri)
        object_proxy.objectType = object_identifier[0]
        object_proxy.objectIdentifier = object_identifier

        # associate this object with its device -- layer hopping :-/
        self.graph.graph.add((self.device_iri, BACnetNS.hasObject, object_iri))

        return object_proxy

    def find_object(self, object_identifier: ObjectIdentifier) -> Optional[ObjectProxy]:
        """Given an object identifier return an ObjectProxy for the object."""
        return None

    def delete_object(
        self,
        object_identifier: ObjectIdentifier,
    ) -> None:
        """Given an object identifier find the existing ObjectProxy for the
        object and delete all of its associated nodes.
        """
        # object_iri = _object_node(self.device_iri, object_identifier)
        # self.graph.remove((self.device_iri, BACnetNS.hasObject, object_iri))
        pass


#
#   ObjectProxy
#


@bacpypes_debugging
class ObjectProxy:
    """
    A proxy for getting and setting property values of an object.
    """

    _debug: Callable[..., None]

    _graph: BACnetGraph
    _object_iri: URIRef
    _object_cls: Optional[type]

    def __init__(
        self, graph: BACnetGraph, object_iri: URIRef, object_cls: Optional[type] = None
    ) -> None:
        if _debug:
            ObjectProxy._debug("__init__ %r %r", graph, object_iri)

        self._graph = graph
        self._object_iri = object_iri

        ###TODO look up the object subclass if it hasn't been provided
        self._object_cls = object_cls

    def __getattr__(self, attr: str) -> Any:
        if attr.startswith("_"):  #  or (attr not in self._elements):
            return object.__getattribute__(self, attr)
        if _debug:
            ObjectProxy._debug("__getattr__ %r", attr)

        s = self._object_iri
        p = attr_to_predicate(attr)

        # uses the convenience function for functional properties
        o = self._graph.value(s, p, default=None)
        if o is None:
            raise AttributeError(attr)

        # attempt to interpret the thing as a primitive or constructed value
        value: Any
        if (self._object_cls is None) or (self._object_cls not in self._elements):
            value = o
        else:
            raise NotImplementedError(attr)

        return value

    def __setattr__(self, attr: str, value: Any) -> None:
        if attr.startswith("_"):  # (attr not in self._elements) or (value is None):
            super().__setattr__(attr, value)
            return
        if _debug:
            ObjectProxy._debug("__setattr__ %r %r", attr, value)

        g = self._graph.graph
        s = self._object_iri
        p = attr_to_predicate(attr)

        if isinstance(value, Literal):
            o = value
        elif isinstance(value, Atomic):
            o = atomic_encode(self._graph, value)
        elif isinstance(value, Sequence):
            o = _blank_node()
            sequence_to_graph(value, o, self._graph)
        else:
            o = Literal(value)

        # uses the convenience function which removes existing triples for
        # functional properties
        g.set((s, p, o))
