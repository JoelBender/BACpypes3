#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test RDF network topology
-------------------------
"""

import unittest

from rdflib import Graph, Literal, URIRef  # type: ignore[import]
from rdflib import namespace  # type: ignore[import]

RDF, RDFS = namespace.RDF, namespace.RDFS

from bacpypes3.debugging import ModuleLogger
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import NetworkType
from bacpypes3.rdf import BACnetGraph
from bacpypes3.rdf.core import BACNET, set_identifier_functions

# some debugging
_debug = 0
_log = ModuleLogger(globals())


class TestNetworkTopology(unittest.TestCase):
    def setUp(self):
        self.g = Graph()
        self.bacnet_graph = BACnetGraph(self.g)

    def test_create_network(self):
        net = self.bacnet_graph.create_network(2000, NetworkType("mstp"))

        assert net == URIRef("bacnet://network/2000")
        assert (net, RDF.type, BACNET.Network) in self.g
        assert (
            net,
            BACNET["network-number"],
            Literal(2000, datatype=namespace.XSD.nonNegativeInteger),
        ) in self.g
        assert (net, BACNET["network-type"], BACNET["NetworkType.mstp"]) in self.g

    def test_create_network_is_idempotent(self):
        a = self.bacnet_graph.create_network(5, NetworkType("ipv4"))
        b = self.bacnet_graph.create_network(5)

        assert a == b
        assert len(list(self.g.objects(a, BACNET["network-number"]))) == 1
        assert list(self.g.objects(a, BACNET["network-type"])) == [
            BACNET["NetworkType.ipv4"]
        ]

    def test_create_router(self):
        router = self.bacnet_graph.create_router(
            Address("192.168.0.200"), networks=[2000, 3000]
        )

        assert (router, RDF.type, BACNET.Router) in self.g
        assert (router, RDFS.label, Literal("192.168.0.200")) in self.g
        routed = set(self.g.objects(router, BACNET["routes-to-network"]))
        assert routed == {
            URIRef("bacnet://network/2000"),
            URIRef("bacnet://network/3000"),
        }
        for net in routed:
            assert (net, RDF.type, BACNET.Network) in self.g

    def test_device_topology_and_reachability(self):
        router = self.bacnet_graph.create_router(
            Address("192.168.0.200"), networks=[2000]
        )
        net = self.bacnet_graph.create_network(2000, NetworkType("mstp"))
        device_graph = self.bacnet_graph.create_device(
            Address("2000:7"), ObjectIdentifier("device,7")
        )
        device_graph.set_network(net)
        device_graph.set_router(router)
        device_graph.set_reachable(True)
        device_graph.set_reachable(False)

        dev = device_graph.device_iri
        assert (dev, BACNET["on-network"], net) in self.g
        assert (dev, BACNET["reached-via"], router) in self.g
        assert list(self.g.objects(dev, BACNET.reachable)) == [Literal(False)]

        # the device address and the network share the same network number
        rows = list(
            self.g.query(
                """
                SELECT ?dev ?type WHERE {
                    ?dev bacnet:device-address [ bacnet:network-number ?n ] ;
                         bacnet:on-network ?net .
                    ?net bacnet:network-number ?n ;
                         bacnet:network-type ?type .
                }
                """,
                initNs={"bacnet": BACNET},
            )
        )
        assert [(r.dev, r.type) for r in rows] == [(dev, BACNET["NetworkType.mstp"])]

    def test_custom_identifier_functions(self):
        set_identifier_functions(
            network_node_fn=lambda n: URIRef("urn:example:net:" + str(n)),
            router_node_fn=lambda a: URIRef("urn:example:router:" + str(a)),
        )
        try:
            router = self.bacnet_graph.create_router(Address("10.0.0.1"), [1])
            assert router == URIRef("urn:example:router:10.0.0.1")
            assert (
                router,
                BACNET["routes-to-network"],
                URIRef("urn:example:net:1"),
            ) in self.g
        finally:
            set_identifier_functions()


if __name__ == "__main__":
    unittest.main()
