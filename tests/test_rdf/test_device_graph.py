#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test RDF DeviceGraph
--------------------
"""

import unittest

from rdflib import Graph  # type: ignore[import]
from rdflib.namespace import RDF  # type: ignore[import]

from bacpypes3.debugging import ModuleLogger
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.rdf import BACnetGraph
from bacpypes3.rdf.core import BACNET

# some debugging
_debug = 0
_log = ModuleLogger(globals())


class TestDeviceGraph(unittest.TestCase):
    def test_create_object_types_object(self):
        g = Graph()
        device_graph = BACnetGraph(g).create_device(
            Address("192.168.0.10"), ObjectIdentifier("device,1")
        )
        obj = device_graph.create_object(ObjectIdentifier("analog-input,1"))

        # the object node is typed like the device node
        assert (obj._object_iri, RDF.type, BACNET.Object) in g
        assert (device_graph.device_iri, RDF.type, BACNET.Device) in g
        assert (device_graph.device_iri, BACNET.contains, obj._object_iri) in g

    def test_every_object_is_typed(self):
        g = Graph()
        device_graph = BACnetGraph(g).create_device(
            Address("192.168.0.10"), ObjectIdentifier("device,1")
        )
        for objid in ("device,1", "analog-value,2", "binary-output,3"):
            device_graph.create_object(ObjectIdentifier(objid))

        contained = set(g.objects(device_graph.device_iri, BACNET.contains))
        typed = set(g.subjects(RDF.type, BACNET.Object))
        assert len(contained) == 3
        assert contained == typed

    def test_object_type_query(self):
        g = Graph()
        device_graph = BACnetGraph(g).create_device(
            Address("192.168.0.10"), ObjectIdentifier("device,1")
        )
        device_graph.create_object(ObjectIdentifier("analog-output,1"))

        rows = list(
            g.query(
                "SELECT ?o WHERE { ?o a bacnet:Object }",
                initNs={"bacnet": BACNET},
            )
        )
        assert len(rows) == 1


if __name__ == "__main__":
    unittest.main()
