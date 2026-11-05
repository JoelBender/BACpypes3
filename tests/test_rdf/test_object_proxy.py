#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test RDF ObjectProxy
--------------------
"""

import unittest

from rdflib import Graph, Literal  # type: ignore[import]
from rdflib import namespace  # type: ignore[import]
from rdflib.collection import Collection  # type: ignore[import]

from bacpypes3.debugging import ModuleLogger
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import (
    CharacterString,
    ClosingTag,
    ContextTag,
    Date,
    Null,
    ObjectIdentifier,
    OpeningTag,
    Real,
    TagList,
    Time,
    Unsigned,
)
from bacpypes3.constructeddata import Any, AnyAtomic, ArrayOf, ListOf
from bacpypes3.basetypes import (
    AnyAtomicExtended,
    DailySchedule,
    DateTime,
    LogRecord,
    LogRecordLogDatum,
    PriorityArray,
    PriorityValue,
    PropertyValue,
    StatusFlags,
    TimeValue,
)
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


#
#   Any, AnyAtomic and AnyAtomicExtended values
#


def no_python_repr(g):
    ttl = g.serialize(format="turtle")
    assert " object at 0x" not in ttl, ttl
    return ttl


def date_time():
    return DateTime(date=Date("2026-11-04"), time=Time("12:00:00"))


class TestAnyValues(unittest.TestCase):
    def test_anyatomic_schedule_default(self):
        g, obj = object_proxy()
        obj.scheduleDefault = AnyAtomic(Real(72.0))
        no_python_repr(g)
        value = g.value(obj._object_iri, BACNET["schedule-default"])
        assert value == Literal(72.0, datatype=namespace.XSD.float)

    def test_anyatomic_null(self):
        g, obj = object_proxy()
        obj.scheduleDefault = AnyAtomic(Null(()))
        assert g.value(obj._object_iri, BACNET["schedule-default"]) == BACNET.Null

    def test_anyatomic_enumerated(self):
        g, obj = object_proxy()
        obj.relinquishDefault = AnyAtomic(Unsigned(1))
        value = g.value(obj._object_iri, BACNET["relinquish-default"])
        assert value == Literal(1, datatype=namespace.XSD.nonNegativeInteger)

    def test_anyatomicextended_datetime(self):
        g, obj = object_proxy()
        obj.presentValue = AnyAtomicExtended(date_time())
        no_python_repr(g)
        value = g.value(obj._object_iri, BACNET["present-value"])
        assert value.datatype == namespace.XSD.dateTime

    def test_datetime_same_inside_and_outside_sequence(self):
        g, obj = object_proxy()
        obj.timeOfDeviceRestart = date_time()
        value = g.value(obj._object_iri, BACNET["time-of-device-restart"])
        assert value.datatype == namespace.XSD.dateTime

    def test_list_of_anyatomic(self):
        g, obj = object_proxy()
        obj.listOfValues = ListOf(AnyAtomic)(
            [AnyAtomic(Real(1.0)), AnyAtomic(Null(()))]
        )
        no_python_repr(g)
        node = g.value(obj._object_iri, BACNET["list-of-values"])
        assert list(Collection(g, node)) == [
            Literal(1.0, datatype=namespace.XSD.float),
            BACNET.Null,
        ]

    def test_weekly_schedule(self):
        g, obj = object_proxy()
        tv = TimeValue(time=Time("08:00:00"), value=AnyAtomic(Real(70.0)))
        obj.weeklySchedule = ArrayOf(DailySchedule)([DailySchedule(daySchedule=[tv])])
        ttl = no_python_repr(g)
        assert '"70.0"^^xsd:float' in ttl

    def test_property_value_any(self):
        g, obj = object_proxy()
        obj.listOfInitializationValues = ListOf(PropertyValue)(
            [
                PropertyValue(
                    propertyIdentifier="present-value",
                    value=Any(Real(5.0)),
                    priority=8,
                )
            ]
        )
        no_python_repr(g)
        node = g.value(obj._object_iri, BACNET["list-of-initialization-values"])
        (pv,) = list(Collection(g, node))
        assert g.value(pv, BACNET["value"]) == Literal(
            5.0, datatype=namespace.XSD.float
        )
        assert g.value(pv, BACNET["priority"]) == Literal(
            8, datatype=namespace.XSD.nonNegativeInteger
        )

    def test_log_record_any_value(self):
        g, obj = object_proxy()
        lr = LogRecord(
            timestamp=date_time(),
            logDatum=LogRecordLogDatum(anyValue=Any(Real(1.0))),
        )
        obj.logBuffer = ListOf(LogRecord)([lr])
        no_python_repr(g)
        (rec,) = list(Collection(g, g.value(obj._object_iri, BACNET["log-buffer"])))
        datum = g.value(rec, BACNET["log-datum"])
        assert g.value(datum, BACNET["any-value"]) == Literal(
            1.0, datatype=namespace.XSD.float
        )
        assert g.value(rec, BACNET["timestamp"]).datatype == namespace.XSD.dateTime

    def test_any_constructed_as_tag_list(self):
        g, obj = object_proxy()
        # several tags, the type is not known without the property context
        any_value = Any(
            TagList(
                [
                    Real(1.0).encode()[0],
                    ObjectIdentifier("analog-value,1").encode()[0],
                    OpeningTag(3),
                    ContextTag(0, b""),
                    ClosingTag(3),
                ]
            )
        )
        obj.mystery = any_value
        no_python_repr(g)
        node = g.value(obj._object_iri, BACNET["mystery"])
        tags = list(Collection(g, g.value(node, BACNET["any"])))

        # one node per tag, the same shape as Any.dict_contents()
        expected = any_value.dict_contents()["any"]
        assert len(tags) == len(expected) == 5
        assert g.value(tags[0], BACNET["real"]) == Literal(
            1.0, datatype=namespace.XSD.float
        )
        assert str(g.value(tags[1], BACNET["object-identifier"])) == "analog-value,1"
        assert g.value(tags[2], BACNET["open"]).toPython() == 3
        assert g.value(tags[3], BACNET["context"]).toPython() == 0
        assert str(g.value(tags[3], BACNET["data"])) == "05"
        assert g.value(tags[4], BACNET["close"]).toPython() == 3

    def test_any_context_wrapped_single_value(self):
        g, obj = object_proxy()
        tag_list = TagList([OpeningTag(0), Real(1.0).encode()[0], ClosingTag(0)])
        obj.mystery = Any(tag_list)
        value = g.value(obj._object_iri, BACNET["mystery"])
        assert value == Literal(1.0, datatype=namespace.XSD.float)

    def test_unknown_python_object_raises(self):
        g, obj = object_proxy()
        with self.assertRaises(TypeError):
            obj.presentValue = object()
        assert g.value(obj._object_iri, BACNET["present-value"]) is None
