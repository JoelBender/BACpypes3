"""
Core
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional
from urllib.parse import quote

from rdflib import Graph, Literal, BNode, URIRef  # type: ignore[import]
from rdflib.namespace import Namespace, RDF, RDFS, XSD  # type: ignore[import]
from rdflib.plugins.sparql import prepareQuery  # type: ignore[import]

from ..debugging import bacpypes_debugging, ModuleLogger, btox

from ..pdu import Address
from ..primitivedata import (
    Atomic,
    Element,
    ObjectIdentifier,
)
from ..basetypes import DateTime, NetworkType, PropertyIdentifier
from ..constructeddata import Sequence, ExtendedList

from .util import (
    atomic_encode,
    unsigned_encode,
    octetstring_encode,
    enumerated_encode,
    attr_to_predicate,
    sequence_to_graph,
    extendedlist_to_graph,
    value_encode,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


BACNET = Namespace("http://data.ashrae.org/bacnet/")
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


def network_node(network_number: int) -> URIRef:
    """Given a network number return a URI reference for the network.  The
    default is bacnet://network/<number>, which cannot collide with the
    Annex Q.8 device form bacnet://<instance>; the local network is 0."""
    return BACnetURI["//network/" + str(network_number)]


def router_node(router_address: Address) -> URIRef:
    """Given the address of a router return a URI reference for it, the
    default is bacnet://router/<address>."""
    return BACnetURI["//router/" + quote(str(router_address), safe=":.")]


_device_node: Callable[..., URIRef] = device_node
_object_node: Callable[..., URIRef] = object_node
_blank_node: Callable[..., URIRef] = blank_node
_network_node: Callable[..., URIRef] = network_node
_router_node: Callable[..., URIRef] = router_node


def set_identifier_functions(
    *,
    device_node_fn: Callable[..., URIRef] = device_node,
    object_node_fn: Callable[..., URIRef] = object_node,
    blank_node_fn: Callable[..., URIRef] = blank_node,
    network_node_fn: Callable[..., URIRef] = network_node,
    router_node_fn: Callable[..., URIRef] = router_node,
):
    """This function allows the application using the library to provide
    its own functions for contsructing URI node identifiers for
    devices, objects and blank nodes.
    """
    global _device_node, _object_node, _blank_node, _network_node, _router_node

    _device_node = device_node_fn
    _object_node = object_node_fn
    _blank_node = blank_node_fn
    _network_node = network_node_fn
    _router_node = router_node_fn


#
#   Common prepared queries
#


def bacnet_query(query: str) -> Any:
    """Prepare a SPARQL query with the BACnet namespace prefix included.
    The prepared query is provided to the `BACnetGraph.query()` method
    along with initial variable bindings if they have been provided.
    """
    return prepareQuery(query, initNs={"bacnet": BACNET})


find_device_by_address = bacnet_query(
    """
    select ?s where { ?s bacnet:device-address [
        bacnet:network-number ?net ;
        bacnet:mac-address ?addr
        ] }
    """
)
find_device_by_instance = bacnet_query(
    "select ?s where { ?s bacnet:device-instance ?device_instance .}"
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
        if hasattr(self.graph, "namespace_manager"):
            self.graph.namespace_manager.bind("bacnet", URIRef(BACNET))

    def bind_namespace(self, prefix: str, uri: str) -> Namespace:
        """
        Create a Namespace and bind a prefix to it in the graph.
        """
        namespace = Namespace(uri)
        if hasattr(self.graph, "namespace_manager"):
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
        self.graph.add((device_iri, RDF.type, BACNET.Device))

        if device_address is not None:
            device_address_iri = _blank_node()
            self.graph.add((device_iri, BACNET["device-address"], device_address_iri))

            # encode the network portion, local stations are network 0
            self.graph.add(
                (device_address_iri, RDFS.label, Literal(str(device_address)))
            )

            if device_address.addrNet is None:
                device_address_net = unsigned_encode(self.graph, 0)
            else:
                device_address_net = unsigned_encode(self.graph, device_address.addrNet)

            # encode the MAC address
            device_address_mac = octetstring_encode(self.graph, device_address.addrAddr)

            device_address_proxy = ObjectProxy(self, device_address_iri)
            device_address_proxy.networkNumber = device_address_net
            device_address_proxy.macAddress = device_address_mac

        if device_identifier is not None:
            self.graph.add(
                (device_iri, BACNET["device-instance"], Literal(device_identifier[1]))
            )

        return DeviceGraph(self, device_iri)

    def create_network(
        self,
        network_number: int,
        network_type: Optional[NetworkType] = None,
    ) -> URIRef:
        """Optional network topology: return the node for a BACnet network,
        typed bacnet:Network with its bacnet:network-number (the same value
        used in device addresses, the local network is 0) and, when it is
        known, its link layer as bacnet:network-type (a NetworkType value
        such as ipv4 or mstp, as in the Network Port object).
        """
        network_iri = _network_node(network_number)
        self.graph.add((network_iri, RDF.type, BACNET.Network))
        self.graph.set(
            (
                network_iri,
                BACNET["network-number"],
                unsigned_encode(self.graph, network_number),
            )
        )
        if network_type is not None:
            self.graph.set(
                (
                    network_iri,
                    BACNET["network-type"],
                    enumerated_encode(self.graph, NetworkType(network_type)),
                )
            )
        return network_iri

    def create_router(
        self,
        router_address: Address,
        networks: Iterable[int] = (),
    ) -> URIRef:
        """Optional network topology: return the node for a router found at
        an address (for example from I-Am-Router-To-Network), typed
        bacnet:Router, labeled with its address and linked with
        bacnet:routes-to-network to each network it reports.
        """
        router_iri = _router_node(router_address)
        self.graph.add((router_iri, RDF.type, BACNET.Router))
        self.graph.set((router_iri, RDFS.label, Literal(str(router_address))))
        for network_number in networks:
            network_iri = self.create_network(network_number)
            self.graph.add((router_iri, BACNET["routes-to-network"], network_iri))
        return router_iri

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
        self.graph.graph.add((self.device_iri, BACNET.contains, object_iri))

        return object_proxy

    def set_network(self, network_iri: URIRef) -> None:
        """Optional network topology: the network the device is on
        (bacnet:on-network), see BACnetGraph.create_network()."""
        self.graph.graph.set((self.device_iri, BACNET["on-network"], network_iri))

    def set_router(self, router_iri: URIRef) -> None:
        """Optional network topology: the router the device is reached
        through (bacnet:reached-via), see BACnetGraph.create_router()."""
        self.graph.graph.set((self.device_iri, BACNET["reached-via"], router_iri))

    def set_reachable(self, reachable: bool) -> None:
        """Optional discovery status: whether the device answered when the
        graph was built (bacnet:reachable), so a network or routing problem
        can be told apart from a device that is present but faulted."""
        self.graph.graph.set(
            (self.device_iri, BACNET.reachable, Literal(bool(reachable)))
        )

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
        # self.graph.remove((self.device_iri, BACNET.contains, object_iri))
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

        if isinstance(value, (Literal, URIRef, BNode)):
            o = value
        elif isinstance(value, ExtendedList):
            # ArrayOf/ListOf/SequenceOf become RDF lists; extendedlist_to_graph
            # adds the (s, p, list) triple itself, so replace any existing value
            g.remove((s, p, None))
            extendedlist_to_graph(value, s, p, g)
            return
        elif isinstance(value, Sequence) and not isinstance(value, DateTime):
            o = _blank_node()
            sequence_to_graph(value, o, g)
        elif isinstance(value, Element):
            # atomic values, DateTime, Any, AnyAtomic (schedule-default,
            # relinquish-default, ...); the encoders add triples (bit strings
            # as RDF lists), so they need the rdflib Graph, not the wrapper.
            # Raises TypeError rather than writing a Python repr.
            o = value_encode(g, value)
        elif isinstance(value, (str, int, float, bool)):
            o = Literal(value)
        else:
            raise TypeError(f"{attr}: unable to encode {type(value).__name__}")

        # uses the convenience function which removes existing triples for
        # functional properties
        g.set((s, p, o))
