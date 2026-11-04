#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Base Types CSML dataRev 31
-------------------------------

Directory and authorization base types added in CSML dataRev 31, with the
expected octets computed by hand from the ASN.1 productions.
"""

import pytest

from bacpypes3.basetypes import (
    AccessToken,
    AuthorizationConstraint,
    AuthorizationScope,
    AuthorizationScopeStandard,
    AuthorizationServer,
    DateTime,
    DeviceAddressProxyTableEntry,
    DeviceQualifier,
    DeviceQualifierInstanceRange,
    DiscoveryState,
    LightingOperation,
    NetworkQualifier,
    NetworkQualifierNetworkRange,
    PropertyStates,
    ResponseIncludes,
    ServicesSupported,
)
from bacpypes3.debugging import ModuleLogger, xtob
from bacpypes3.json.util import json_to_sequence, sequence_to_json
from bacpypes3.pdu import PDUData
from bacpypes3.primitivedata import ObjectType, PropertyIdentifier, TagList

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def encode(obj) -> bytes:
    return obj.encode().encode().pduData


def decode(cls, data: bytes):
    tag_list = TagList.decode(PDUData(data))
    obj = cls.decode(tag_list)
    assert len(tag_list) == 0
    return obj


def test_device_qualifier():
    assert encode(DeviceQualifier(all=())) == xtob("08")
    assert encode(DeviceQualifier(instanceSet=[1, 2])) == xtob("1e 2101 2102 1f")

    obj = DeviceQualifier(
        instanceRange=DeviceQualifierInstanceRange(instanceLow=1, instanceHigh=300)
    )
    assert encode(obj) == xtob("2e 2101 22012c 2f")
    assert decode(DeviceQualifier, encode(obj)).instanceRange.instanceHigh == 300

    obj = DeviceQualifier(pattern="AHU*")
    assert encode(obj) == xtob("3d 05 0041 48552a")
    assert decode(DeviceQualifier, encode(obj)).pattern == "AHU*"


def test_network_qualifier_range():
    obj = NetworkQualifier(
        networkRange=NetworkQualifierNetworkRange(
            networkNumberRangeLowLimit=5, networkNumberRangeHighLimit=10
        )
    )
    assert encode(obj) == xtob("2e 2105 210a 2f")
    result = decode(NetworkQualifier, encode(obj))
    assert result.networkRange.networkNumberRangeHighLimit == 10

    with pytest.raises(ValueError):
        NetworkQualifierNetworkRange(networkNumberRangeLowLimit=65536)


def test_property_states_directory_choices():
    """response-includes [260] and discovery-state [261] use extended-value."""
    obj = PropertyStates(discoveryState=DiscoveryState("complete"))
    # 261 * 100000 + 2 = 26100002 = 0x18E4122
    assert encode(obj) == xtob("fc 3f 018e4122")
    result = decode(PropertyStates, encode(obj))
    assert result._choice == "discoveryState"

    obj = PropertyStates(responseIncludes=ResponseIncludes("fullObjects"))
    result = decode(PropertyStates, encode(obj))
    assert result.responseIncludes == ResponseIncludes.fullObjects


def test_authorization_scope():
    assert AuthorizationScopeStandard._bitstring_length == 24
    assert str(AuthorizationScopeStandard(["view", "reserved-9"])) == "view;reserved-9"

    obj = AuthorizationScope(standard=["view", "control"], extended=["site-admin"])
    # 24 bits, 0 unused: view (0) and control (2) are 0xA0
    assert encode(obj) == xtob("84 00a00000 0e 750b 00736974652d61646d696e 0f")
    assert decode(AuthorizationScope, encode(obj)).extended == ["site-admin"]


def test_access_token_round_trip():
    token = AccessToken(
        issuer=1,
        issued=DateTime(date=(126, 1, 2, 5), time=(3, 4, 5, 0)),
        audience=[100, -1],
        client=7,
        constraint=AuthorizationConstraint(
            origin="sameNetwork", authentication="certified"
        ),
        keyId=1,
        signature=b"\x01\x02",
    )
    result = decode(AccessToken, encode(token))
    assert list(result.audience) == [100, -1]
    assert result.constraint.origin == 1
    assert result.signature == b"\x01\x02"


def test_element_names():
    """Names camelCase cannot express are emitted with _element_names."""
    server = AuthorizationServer(authServer=5, signingKey1=b"\x01")
    json = sequence_to_json(server)
    assert set(json) == {"auth-server", "signing-key-1"}
    assert json_to_sequence(json, AuthorizationServer).signingKey1 == b"\x01"

    rdf_util = pytest.importorskip("bacpypes3.rdf.util")
    predicate = rdf_util.element_predicate(server, "signingKey1")
    assert str(predicate).endswith("/signing-key-1")
    entry = DeviceAddressProxyTableEntry()
    assert str(rdf_util.element_predicate(entry, "lastIAmTime")).endswith(
        "/last-i-am-time"
    )


@pytest.mark.parametrize(
    "cls, value, name",
    [
        (PropertyIdentifier, 4194349, "max-proxied-i-ams-per-second"),
        (PropertyIdentifier, 4194347, "authorization-server"),
        (PropertyIdentifier, 4194351, "directory-revision"),
        (ObjectType, 65, "directory"),
        (LightingOperation, 14, "toggle-default"),
    ],
)
def test_new_names(cls, value, name):
    assert cls(value).asn1 == name
    assert cls(name) == value


def test_services_supported_new_bits():
    # dataRev 31 says length 49 but also defines bits 49 and 50
    assert ServicesSupported._bitstring_length == 51
    assert ServicesSupported._bitstring_names["auth-request"] == 49
    assert ServicesSupported._bitstring_names["directory-query"] == 50
