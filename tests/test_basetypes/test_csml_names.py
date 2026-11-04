#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Base Types Standard Names
------------------------------

Enumeration, bit and element names match the names in the CSML description
of Clause 21 (bacnet-data-types.xml) as they are emitted in strings, JSON
keys and RDF predicates.
"""

import pytest

from bacpypes3.apdu import RejectReason, UnconfirmedServiceChoice
from bacpypes3.basetypes import (
    AuthenticationFactorType,
    AuthorizationExemption,
    BackupState,
    EngineeringUnits,
    ErrorCode,
    LockStatus,
    NetworkPortCommand,
    ObjectTypesSupported,
    PriorityFilter,
    PropertyValue,
    ServicesSupported,
    TimeStamp,
    VTClass,
)
from bacpypes3.constructeddata import Any
from bacpypes3.debugging import ModuleLogger
from bacpypes3.json.util import sequence_to_json
from bacpypes3.primitivedata import (
    ObjectType,
    PropertyIdentifier,
    Real,
    attr_to_asn1,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


ENUMERATIONS = [
    # names the attribute name cannot express (_asn1_overrides)
    (EngineeringUnits, 232, "decibels-a"),
    (BackupState, 3, "performing-a-backup"),
    (BackupState, 4, "performing-a-restore"),
    (VTClass, 1, "ansi-x3-64"),
    (VTClass, 5, "hp-700-94"),
    (VTClass, 6, "ibm-3130"),
    (UnconfirmedServiceChoice, 13, "who-am-i"),
    (ErrorCode, 22, "property-is-not-a-list"),
    (ErrorCode, 148, "not-a-bacnet-sc-hub"),
    (ErrorCode, 164, "http-not-a-server"),
    (AuthenticationFactorType, 13, "fasc-n"),
    (AuthenticationFactorType, 16, "fasc-n-large-bcd"),
    (AuthenticationFactorType, 21, "cbeff-a"),
    # renamed attributes
    (EngineeringUnits, 63, "kelvin"),
    (EngineeringUnits, 121, "delta-kelvin"),
    (EngineeringUnits, 122, "kiloohms"),
    (EngineeringUnits, 141, "watts-per-square-meter-per-kelvin"),
    (EngineeringUnits, 237, "ohm-meter-squared-per-meter"),
    (EngineeringUnits, 247, "joules-per-hour"),
    (PropertyIdentifier, 64, "max-manager"),
    (PropertyIdentifier, 169, "auto-subordinate-discovery"),
    (PropertyIdentifier, 172, "subordinate-proxy-enable"),
    (ObjectType, 41, "datepattern-value"),
    (ObjectType, 43, "datetimepattern-value"),
    (ObjectType, 49, "timepattern-value"),
    (NetworkPortCommand, 2, "renew-fd-registration"),
    (NetworkPortCommand, 3, "restart-subordinate-discovery"),
    (LockStatus, 2, "lock-fault"),
    (ErrorCode, 14, "invalid-timestamp"),
    (ErrorCode, 188, "tls-error"),
    (RejectReason, 3, "invalid-parameter-data-type"),
    (AuthenticationFactorType, 10, "wiegand37-facility"),
    (AuthorizationExemption, 6, "authorization-delay"),
    # values added from the CSML
    (EngineeringUnits, 47918, "active-energy-pulse-value"),
    (PropertyIdentifier, 4194304, "max-bvlc-length-accepted"),
    (ObjectType, 64, "color-temperature"),
]


@pytest.mark.parametrize("cls, value, name", ENUMERATIONS)
def test_enumeration_name(cls, value, name):
    assert cls(value).asn1 == name
    assert str(cls(value)) == name
    assert cls(name) == value


def test_override_replaces_derived_name():
    """The name derived from the attribute is not also accepted."""
    assert "performing-abackup" not in BackupState._enum_map
    assert BackupState("performingABackup") == 3


BITS = [
    (PriorityFilter, 2, "priority-3"),
    (PriorityFilter, 15, "priority-16"),
    (ServicesSupported, 47, "who-am-i"),
    (ObjectTypesSupported, 41, "datepattern-value"),
    (ObjectTypesSupported, 31, "timer"),
]


@pytest.mark.parametrize("cls, bit, name", BITS)
def test_bit_name(cls, bit, name):
    assert cls._bitstring_names[name] == bit
    assert str(cls([name])) == name


def test_services_supported_matches_service_choices():
    """get_services_supported() maps service choice names onto bit names."""
    attr = UnconfirmedServiceChoice(13).attr
    assert attr == "whoAmI"
    assert getattr(ServicesSupported, attr) == 47


ELEMENTS = [
    ("propertyValue", "property-value"),
    ("propertyArrayIndex", "property-array-index"),
    ("deviceIdentifier", "device-identifier"),
    ("listOfReadAccessSpecifications", "list-of-read-access-specifications"),
    ("enumeratedValue", "enumerated-value"),
    ("integerValue", "integer-value"),
    ("timestamp", "timestamp"),
    ("datetime", "datetime"),
    ("eventTimestamps", "event-timestamps"),
    ("weeknday", "weeknday"),
    ("bacnetipAddress", "bacnetip-address"),
    ("changeOfCharacterstring", "change-of-characterstring"),
    ("faultCharacterstring", "fault-characterstring"),
    ("writeSuccessful", "write-successful"),
    ("changeOfStatusFlags", "change-of-status-flags"),
    ("exceededLimit", "exceeded-limit"),
    ("authenticationFactor", "authentication-factor"),
    ("octetstring", "octetstring"),
    ("objectidentifier", "objectidentifier"),
]


@pytest.mark.parametrize("attr, name", ELEMENTS)
def test_element_json_key(attr, name):
    assert attr_to_asn1(attr) == name


@pytest.mark.parametrize("attr, name", ELEMENTS)
def test_element_rdf_predicate(attr, name):
    rdf_util = pytest.importorskip("bacpypes3.rdf.util")
    assert str(rdf_util.attr_to_predicate(attr)).rsplit("/", 1)[1] == name


def test_property_value_json():
    obj = PropertyValue(propertyIdentifier="presentValue", propertyValue=Any(Real(1.0)))
    json = sequence_to_json(obj)
    assert set(json) == {"property-identifier", "property-value"}


def test_time_stamp_json():
    json = sequence_to_json(TimeStamp.as_datetime(0.0))
    assert set(json) == {"datetime"}
