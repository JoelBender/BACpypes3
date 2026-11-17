"""
Test Nested Types
-----------------

The CSML defines some enumerations and bit strings inline, inside the sequence
that uses them, like the status of a BACnetRouterEntry.  These are nested
classes like RouterEntry.Status, so their RDF names follow the CSML structure
(bacnet:RouterEntry.Status.busy) and match the csml2rdf shapes.  The older
top-level names are aliases.
"""

from __future__ import annotations

import pytest
from rdflib import Graph, URIRef  # type: ignore[import]

from bacpypes3 import apdu, basetypes
from bacpypes3.constructeddata import Sequence
from bacpypes3.debugging import ModuleLogger
from bacpypes3.primitivedata import Enumerated, Unsigned
from bacpypes3.rdf.core import BACNET
from bacpypes3.rdf.util import (
    bitstring_decode,
    bitstring_encode,
    enumerated_decode,
    enumerated_encode,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# (module, parent, nested, member, old name)
MOVED = [
    (basetypes, "RouterEntry", "Status", "status", "RouterEntryStatus"),
    (
        basetypes,
        "AccumulatorRecord",
        "AccumulatorStatus",
        "accumulatorStatus",
        "AccumulatorRecordAccumulatorStatus",
    ),
    (
        basetypes,
        "AccessRule",
        "TimeRangeSpecifier",
        "timeRangeSpecifier",
        "AccessRuleTimeRangeSpecifier",
    ),
    (
        basetypes,
        "AccessRule",
        "LocationSpecifier",
        "locationSpecifier",
        "AccessRuleLocationSpecifier",
    ),
    (
        basetypes,
        "AuthorizationConstraint",
        "Origin",
        "origin",
        "AuthorizationConstraintOrigin",
    ),
    (
        basetypes,
        "AuthorizationConstraint",
        "Authentication",
        "authentication",
        "AuthorizationConstraintAuthentication",
    ),
    (
        basetypes,
        "AuthorizationScope",
        "Standard",
        "standard",
        "AuthorizationScopeStandard",
    ),
    (basetypes, "Error", "ErrorClass", "errorClass", "ErrorClass"),
    (basetypes, "Error", "ErrorCode", "errorCode", "ErrorCode"),
    (
        apdu,
        "GetEnrollmentSummaryRequest",
        "AcknowledgmentFilter",
        "acknowledgmentFilter",
        "GetEnrollmentSummaryRequestAcknowledgmentFilterType",
    ),
    (
        apdu,
        "GetEnrollmentSummaryRequest",
        "EventStateFilter",
        "eventStateFilter",
        "GetEnrollmentSummaryRequestEventStateFilterType",
    ),
    (
        apdu,
        "ConfirmedTextMessageRequest",
        "MessagePriority",
        "messagePriority",
        "ConfirmedTextMessageRequestMessagePriority",
    ),
    (
        apdu,
        "UnconfirmedTextMessageRequest",
        "MessagePriority",
        "messagePriority",
        "UnconfirmedTextMessageRequestMessagePriority",
    ),
    (
        apdu,
        "DeviceCommunicationControlRequest",
        "EnableDisable",
        "enableDisable",
        "DeviceCommunicationControlRequestEnableDisable",
    ),
    (
        apdu,
        "ReinitializeDeviceRequest",
        "ReinitializedStateOfDevice",
        "reinitializedStateOfDevice",
        "ReinitializeDeviceRequestReinitializedStateOfDevice",
    ),
]


def hexlify(obj) -> str:
    """Encode an element and return the octets as a hex string."""
    return obj.encode().encode().pduData.hex()


def test_nested_class_is_not_an_element():
    class Outer(Sequence):
        _order = ("value", "state")

        class State(Enumerated):
            idle = 0
            busy = 1

        value = Unsigned(_context=0)
        state = State(_context=1)

    assert list(Outer._elements) == ["value", "state"]
    assert "State" not in Outer._elements
    assert issubclass(Outer._elements["state"], Outer.State)

    obj = Outer(value=1, state="busy")
    assert obj.state == Outer.State.busy


@pytest.mark.parametrize("module, parent, nested, member, old", MOVED)
def test_moved_type(module, parent, nested, member, old):
    parent_class = getattr(module, parent)
    nested_class = getattr(parent_class, nested)

    # the old name is an alias, in basetypes for all of them
    assert getattr(module, old) is nested_class
    assert getattr(basetypes, old) is nested_class

    # the element is the nested type with its context tag, and keeps the name
    element_type = parent_class._elements[member]
    assert issubclass(element_type, nested_class)
    assert element_type.__qualname__ == f"{parent}.{nested}"
    assert nested not in parent_class._elements


def test_error_names():
    assert basetypes.ErrorType is basetypes.Error
    assert basetypes.ErrorClass is basetypes.Error.ErrorClass
    assert basetypes.ErrorCode is basetypes.Error.ErrorCode

    # the Error-PDU uses the same enumerations
    assert issubclass(apdu.Error._elements["errorClass"], basetypes.Error.ErrorClass)
    assert issubclass(apdu.Error._elements["errorCode"], basetypes.Error.ErrorCode)


def test_unknown_basetypes_name():
    with pytest.raises(AttributeError):
        basetypes.NoSuchTypeAnywhere  # noqa: B018


def test_wire_encoding_unchanged():
    # the octets recorded before the types were nested
    entry = basetypes.RouterEntry(networkNumber=5, macAddress=b"\x01", status=1)
    assert hexlify(entry) == "090519012901"

    error = basetypes.Error(errorClass="object", errorCode="unknown-object")
    assert hexlify(error) == "9101911f"

    pdu = apdu.Error(
        service_choice=12, errorClass="property", errorCode="unknown-property"
    )
    pdu.apduInvokeID = 7
    assert pdu.encode().pduData.hex() == "91029120"


@pytest.mark.parametrize(
    "value, iri",
    [
        (basetypes.RouterEntry.Status("busy"), "RouterEntry.Status.busy"),
        (basetypes.Error.ErrorClass("object"), "Error.ErrorClass.object"),
        (
            apdu.ConfirmedTextMessageRequest.MessagePriority("urgent"),
            "ConfirmedTextMessageRequest.MessagePriority.urgent",
        ),
    ],
)
def test_enumerated_rdf_names(value, iri):
    g = Graph()
    encoded = enumerated_encode(g, value)
    assert encoded == URIRef(BACNET[iri])
    assert enumerated_decode(g, encoded, value.__class__) == value


def test_context_tagged_enumerated_rdf_name():
    # the element type of RouterEntry.status has a context tag
    status_type = basetypes.RouterEntry._elements["status"]
    value = status_type("disconnected")
    assert (
        enumerated_encode(Graph(), value) == BACNET["RouterEntry.Status.disconnected"]
    )


def test_enumerated_decode_wrong_class():
    with pytest.raises(ValueError):
        enumerated_decode(
            Graph(), BACNET["BinaryPV.active"], basetypes.RouterEntry.Status
        )


def test_bitstring_rdf_names():
    g = Graph()
    value = basetypes.AuthorizationScope.Standard(["auth", "bind"])
    head = bitstring_encode(g, value)
    names = {str(item).replace(str(BACNET), "") for item in g.items(head)}
    assert names == {
        "AuthorizationScope.Standard.auth",
        "AuthorizationScope.Standard.bind",
    }
    assert bitstring_decode(g, head, basetypes.AuthorizationScope.Standard) == value


def test_local_class_falls_back_to_name():
    class Local(Enumerated):
        one = 1

    # a class defined in a function has <locals> in its qualified name
    assert "<locals>" in Local.__qualname__
    assert enumerated_encode(Graph(), Local("one")) == BACNET["Local.one"]
