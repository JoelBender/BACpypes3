#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test APDU Services CSML dataRev 31
----------------------------------

The DirectoryQuery and AuthRequest services added in CSML dataRev 31 encode
into APDUs and decode back into the same classes.
"""

from bacpypes3.apdu import (
    AuthRequestACK,
    AuthRequestError,
    AuthRequestRequest,
    DirectoryQueryACK,
    DirectoryQueryRequest,
    ErrorType,
    error_types,
)
from bacpypes3.basetypes import (
    AuthorizationScope,
    AuthRequestRequestTokenRequest,
    DeviceQualifier,
)
from bacpypes3.debugging import ModuleLogger, xtob

from .test_apdu_services import round_trip

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def test_directory_query_request():
    octets, result = round_trip(
        DirectoryQueryRequest(
            deviceQualifier=DeviceQualifier(all=()), responseIncludes="instances"
        ),
        invoke_id=9,
    )
    assert octets == xtob("00 05 09 23 0e 08 0f 4900")
    assert result.deviceQualifier._choice == "all"


def test_directory_query_ack():
    octets, result = round_trip(
        DirectoryQueryACK(directoryRevision=3, deviceInstances=[1, 2]), invoke_id=9
    )
    assert octets == xtob("30 09 23 0903 1e 2101 2102 1f")
    assert list(result.deviceInstances) == [1, 2]
    assert result.deviceDetails is None


def test_auth_request():
    octets, result = round_trip(
        AuthRequestRequest(
            tokenRequest=AuthRequestRequestTokenRequest(
                client=7,
                audience=[-1],
                scope=AuthorizationScope(standard=["view"]),
            )
        ),
        invoke_id=10,
    )
    assert octets == xtob("00 05 0a 22 0e 0907 1e 31ff 1f 2e 8400800000 2f 0f")
    assert list(result.tokenRequest.audience) == [-1]

    octets, result = round_trip(AuthRequestACK(), invoke_id=10)
    assert octets == xtob("30 0a 22")
    assert result.tokenResponse is None


def test_auth_request_error():
    octets, result = round_trip(
        AuthRequestError(
            errorType=ErrorType(errorClass="security", errorCode="other"),
            errorDetails="x",
        ),
        invoke_id=11,
    )
    assert octets == xtob("50 0b 22 0e 9104 9100 0f 1a0078")
    assert result.errorDetails == "x"


def test_directory_query_error():
    """directory-query errors use the plain Error production."""
    octets, _ = round_trip(
        error_types[35](errorClass="property", errorCode="unknownProperty"),
        invoke_id=12,
    )
    assert octets == xtob("50 0c 23 9102 9120")
