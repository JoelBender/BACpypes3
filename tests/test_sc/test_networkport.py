#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BACnet/SC network port object
-----------------------------------
"""

import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.pdu import SecureConnectAddress
from bacpypes3.local.networkport import NetworkPortObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class TestSCNetworkPortObject(unittest.IsolatedAsyncioTestCase):
    _debug = None  # type: ignore[assignment]

    async def test_secure_connect_port(self):
        vmac = SecureConnectAddress.random()
        np = NetworkPortObject(
            vmac,
            scPrimaryHubURI="wss://hub.example.org/",
            scFailoverHubURI="wss://failover.example.org/",
        )
        assert int(np.networkType) == 11  # secure-connect
        assert bytes(np.macAddress) == vmac.addrAddr
        assert str(np.protocolLevel) == "bacnet-application"
        assert str(np.scPrimaryHubURI) == "wss://hub.example.org/"
        assert str(np.scFailoverHubURI) == "wss://failover.example.org/"


if __name__ == "__main__":
    unittest.main()
