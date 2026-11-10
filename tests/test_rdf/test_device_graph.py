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
from bacpypes3.object import AnalogInputObject, Object
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.rdf import BACnetGraph
from bacpypes3.rdf.core import BACNET, class_node, object_class_nodes

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

    def test_namespace(self):
        assert str(BACNET) == "http://data.ashrae.org/bacnet/2024#"

    def test_create_object_class_chain(self):
        g = Graph()
        device_graph = BACnetGraph(g).create_device(
            Address("192.168.0.10"), ObjectIdentifier("device,1")
        )
        obj = device_graph.create_object(ObjectIdentifier("analog-input,1"))

        types = set(g.objects(obj._object_iri, RDF.type))
        assert types == {BACNET.AnalogInputObject, BACNET.Object}

    def test_class_query_without_reasoner(self):
        g = Graph()
        device_graph = BACnetGraph(g).create_device(
            Address("192.168.0.10"), ObjectIdentifier("device,1")
        )
        device_graph.create_object(ObjectIdentifier("analog-input,1"))
        device_graph.create_object(ObjectIdentifier("multi-state-value,2"))

        for class_name, count in (
            ("AnalogInputObject", 1),
            ("MultistateValueObject", 1),
            ("Object", 2),
        ):
            rows = list(
                g.query(
                    f"SELECT ?o WHERE {{ ?o a bacnet:{class_name} }}",
                    initNs={"bacnet": BACNET},
                )
            )
            assert len(rows) == count, class_name

    def test_class_names_match_ontology(self):
        # only the RDF names change, the Python classes keep theirs; look the
        # classes up by name so the test does not depend on ObjectType names
        import bacpypes3.object as objects

        for python_name, class_name in (
            ("MultiStateInputObject", "MultistateInputObject"),
            ("MultiStateOutputObject", "MultistateOutputObject"),
            ("MultiStateValueObject", "MultistateValueObject"),
            ("BitStringValueObject", "BitstringValueObject"),
            ("CharacterStringValueObject", "CharacterstringValueObject"),
            ("OctetStringValueObject", "OctetstringValueObject"),
            ("DateTimeValueObject", "DatetimeValueObject"),
            ("DateTimePatternValueObject", "DatetimePatternValueObject"),
        ):
            object_class = getattr(objects, python_name)
            assert object_class.__name__ == python_name
            object_identifier = ObjectIdentifier((object_class.objectType, 1))
            nodes = object_class_nodes(object_identifier)
            assert nodes == [BACNET[class_name], BACNET.Object], python_name

    def test_proprietary_object_type(self):
        assert object_class_nodes(ObjectIdentifier((128, 1))) == [
            BACNET.ProprietaryObject,
            BACNET.Object,
        ]

    def test_proprietary_subclass_of_standard_object(self):
        class ProprietaryAnalogInputObject(AnalogInputObject):
            pass

        g = Graph()
        device_graph = BACnetGraph(g).create_device(
            Address("192.168.0.10"), ObjectIdentifier("device,1")
        )
        obj = device_graph.create_object(
            ObjectIdentifier("analog-input,1"), ProprietaryAnalogInputObject
        )
        assert object_class_nodes(
            ObjectIdentifier("analog-input,1"), ProprietaryAnalogInputObject
        ) == [
            BACNET.ProprietaryAnalogInputObject,
            BACNET.AnalogInputObject,
            BACNET.Object,
        ]
        assert (obj._object_iri, RDF.type, BACNET.AnalogInputObject) in g

    def test_proprietary_subclass_of_object(self):
        class VendorWidgetObject(Object):
            pass

        assert object_class_nodes(ObjectIdentifier((200, 1)), VendorWidgetObject) == [
            BACNET.VendorWidgetObject,
            BACNET.ProprietaryObject,
            BACNET.Object,
        ]

    def test_class_node_python_names_unchanged(self):
        from bacpypes3.object import MultiStateValueObject, BitStringValueObject

        assert MultiStateValueObject.__name__ == "MultiStateValueObject"
        assert class_node(MultiStateValueObject) == BACNET.MultistateValueObject
        assert class_node(BitStringValueObject) == BACNET.BitstringValueObject

    def test_object_identifier_instance_zero(self):
        g = Graph()
        device_graph = BACnetGraph(g).create_device(
            Address("192.168.0.10"), ObjectIdentifier("device,1")
        )
        obj = device_graph.create_object(ObjectIdentifier("analog-input,0"))
        value = g.value(obj._object_iri, BACNET["object-identifier"])
        assert str(value) == "analog-input,0"
        assert value.datatype is None  # a plain xsd:string


if __name__ == "__main__":
    unittest.main()
