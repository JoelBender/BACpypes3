#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test RDF ObjectProxy
--------------------
"""

import unittest

from rdflib import Graph  # type: ignore[import]
from rdflib.collection import Collection  # type: ignore[import]

from bacpypes3.debugging import ModuleLogger
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import CharacterString, Null, ObjectIdentifier, Real
from bacpypes3.constructeddata import ArrayOf
from bacpypes3.basetypes import PriorityArray, PriorityValue, StatusFlags
from bacpypes3.rdf import BACnetGraph
from bacpypes3.rdf.core import BACNET

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def object_proxy():
    g = Graph()
    device_graph = BACnetGraph(g).create_device(
        Address("192.168.0.10"), ObjectIdentifier("device,1")
    )
    return g, device_graph.create_object(ObjectIdentifier("analog-output,1"))


class TestObjectProxy(unittest.TestCase):
    def test_status_flags_none_set(self):
        g, obj = object_proxy()
        obj.statusFlags = StatusFlags([0, 0, 0, 0])
        node = g.value(obj._object_iri, BACNET["status-flags"])
        assert list(Collection(g, node)) == []

    def test_status_flags_some_set(self):
        g, obj = object_proxy()
        obj.statusFlags = StatusFlags([0, 1, 1, 0])
        node = g.value(obj._object_iri, BACNET["status-flags"])
        assert list(Collection(g, node)) == [
            BACNET["StatusFlags.fault"],
            BACNET["StatusFlags.overridden"],
        ]

    def test_array_of_character_string(self):
        g, obj = object_proxy()
        obj.stateText = ArrayOf(CharacterString)(["Off", "On"])
        node = g.value(obj._object_iri, BACNET["state-text"])
        assert [str(x) for x in Collection(g, node)] == ["Off", "On"]

    def test_priority_array(self):
        g, obj = object_proxy()
        pa = PriorityArray([PriorityValue(null=Null(())) for _ in range(16)])
        pa[7] = PriorityValue(real=Real(12.0))
        obj.priorityArray = pa

        slots = list(Collection(g, g.value(obj._object_iri, BACNET["priority-array"])))
        assert len(slots) == 16
        assert float(g.value(slots[7], BACNET["real"])) == 12.0
        assert g.value(slots[0], BACNET["real"]) is None

    def test_array_replaces_previous_value(self):
        g, obj = object_proxy()
        obj.stateText = ArrayOf(CharacterString)(["Off", "On"])
        obj.stateText = ArrayOf(CharacterString)(["Auto"])
        nodes = list(g.objects(obj._object_iri, BACNET["state-text"]))
        assert len(nodes) == 1
        assert [str(x) for x in Collection(g, nodes[0])] == ["Auto"]
