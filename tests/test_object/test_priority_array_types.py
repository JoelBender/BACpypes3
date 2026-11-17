"""
Test Priority Array Element Types
---------------------------------

The values in a priority array are application tagged, so a binary output
sends priority 16 as a plain enumerated value.  Each object type decodes its
priority array with the choice that matches its present value (for example
OptionalBinaryPV) rather than the generic PriorityValue, so the value comes
back as a BinaryPV and is encoded in RDF as `bacnet:binary-pv`.
"""

from __future__ import annotations

from typing import Any

import pytest
from rdflib import Graph  # type: ignore[import]

from bacpypes3.basetypes import (
    OptionalBinaryPV,
    OptionalReal,
    OptionalUnsigned,
    PriorityArray,
    PriorityValue,
    PropertyIdentifier,
)
from bacpypes3.debugging import ModuleLogger
from bacpypes3.object import (
    AnalogOutputObject,
    BinaryOutputObject,
    BinaryValueObject,
    MultiStateValueObject,
)
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.rdf import BACnetGraph
from bacpypes3.rdf.core import BACNET

# some debugging
_debug = 0
_log = ModuleLogger(globals())

PRIORITY_ARRAY = PropertyIdentifier("priority-array")


def wire_priority_array(**priority_16: Any) -> PriorityArray:
    """
    Return the generic priority array a device would send, fifteen nulls and
    the relinquish value at priority 16, after a round trip through tags.
    """
    return PriorityArray(
        [PriorityValue(null=())] * 15 + [PriorityValue(**priority_16)]
    ).encode()


@pytest.mark.parametrize(
    "object_class, element_class, priority_16, choice, value",
    [
        (BinaryOutputObject, OptionalBinaryPV, {"enumerated": 0}, "binaryPV", 0),
        (BinaryValueObject, OptionalBinaryPV, {"enumerated": 1}, "binaryPV", 1),
        (AnalogOutputObject, OptionalReal, {"real": 2.5}, "real", 2.5),
        (MultiStateValueObject, OptionalUnsigned, {"unsigned": 3}, "unsigned", 3),
    ],
)
def test_decode_priority_array(object_class, element_class, priority_16, choice, value):
    priority_array_type = object_class.get_property_type(PRIORITY_ARRAY)
    assert priority_array_type._subtype is element_class

    priority_array = priority_array_type.decode(wire_priority_array(**priority_16))
    assert [element._choice for element in list(priority_array)[:15]] == ["null"] * 15
    assert priority_array[15]._choice == choice
    assert getattr(priority_array[15], choice) == value


def test_binary_output_priority_array_rdf():
    priority_array_type = BinaryOutputObject.get_property_type(PRIORITY_ARRAY)
    priority_array = priority_array_type.decode(wire_priority_array(enumerated=0))

    g = Graph()
    device_graph = BACnetGraph(g).create_device(
        Address("192.168.0.10"), ObjectIdentifier("device,1")
    )
    obj = device_graph.create_object(
        ObjectIdentifier("binary-output,1"), BinaryOutputObject
    )
    obj.priorityArray = priority_array

    # priority 16 is a binary-pv choice, not a generic enumerated one
    head = g.value(obj._object_iri, BACNET["priority-array"])
    elements = list(g.items(head))
    assert len(elements) == 16
    assert g.value(elements[15], BACNET["binary-pv"]) == BACNET["BinaryPV.inactive"]
    assert g.value(elements[15], BACNET["enumerated"]) is None
