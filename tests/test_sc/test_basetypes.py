#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BACnet/SC base types and property identifiers
--------------------------------------------------

Locks the standard enumeration values (ASHRAE 135-2024 Clause 21) so they
cannot drift, and checks the SC constructed datatypes are well formed.
"""

import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.primitivedata import PropertyIdentifier
from bacpypes3.basetypes import (
    NetworkType,
    SCConnectionState,
    SCHubConnectorState,
    SCHubConnection,
    SCDirectConnection,
    SCHubFunctionConnection,
    SCFailedConnectionRequest,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class TestNetworkType(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_secure_connect_value(self):
        assert int(NetworkType.secureConnect) == 11


@bacpypes_debugging
class TestPropertyIdentifiers(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_values(self):
        expected = {
            "deviceUUID": 507,
            "certificateSigningRequestFile": 509,
            "issuerCertificateFiles": 511,
            "maxBvlcLengthAccepted": 4194304,
            "maxNpduLengthAccepted": 4194305,
            "operationalCertificateFile": 4194306,
            "scConnectWaitTimeout": 4194308,
            "scDirectConnectAcceptEnable": 4194309,
            "scDirectConnectAcceptURIs": 4194310,
            "scDirectConnectBinding": 4194311,
            "scDirectConnectConnectionStatus": 4194312,
            "scDirectConnectInitiateEnable": 4194313,
            "scDisconnectWaitTimeout": 4194314,
            "scFailedConnectionRequests": 4194315,
            "scFailoverHubConnectionStatus": 4194316,
            "scFailoverHubURI": 4194317,
            "scHubConnectorState": 4194318,
            "scHubFunctionAcceptURIs": 4194319,
            "scHubFunctionBinding": 4194320,
            "scHubFunctionConnectionStatus": 4194321,
            "scHubFunctionEnable": 4194322,
            "scHeartbeatTimeout": 4194323,
            "scPrimaryHubConnectionStatus": 4194324,
            "scPrimaryHubURI": 4194325,
            "scMaximumReconnectTime": 4194326,
            "scMinimumReconnectTime": 4194327,
        }
        for name, value in expected.items():
            assert int(getattr(PropertyIdentifier, name)) == value, name


@bacpypes_debugging
class TestSCDatatypes(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_connection_state(self):
        assert int(SCConnectionState.notConnected) == 0
        assert int(SCConnectionState.connected) == 1
        assert int(SCConnectionState.disconnectedWithErrors) == 2
        assert int(SCConnectionState.failedToConnect) == 3

    def test_hub_connector_state(self):
        assert int(SCHubConnectorState.noHubConnection) == 0
        assert int(SCHubConnectorState.connectedToPrimary) == 1
        assert int(SCHubConnectorState.connectedToFailover) == 2

    def test_sequences_order(self):
        assert SCHubConnection._order[0] == "connectionState"
        assert SCDirectConnection._order[0] == "uri"
        assert "peerVMAC" in SCDirectConnection._order
        assert "peerUUID" in SCDirectConnection._order
        assert SCHubFunctionConnection._order[3] == "peerAddress"
        assert SCFailedConnectionRequest._order[0] == "timestamp"


if __name__ == "__main__":
    unittest.main()
