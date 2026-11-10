#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BACnet/SC Address (VMAC)
-----------------------------
"""

import unittest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.pdu import Address, SecureConnectAddress, network_types

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class TestSecureConnectAddress(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def test_registered(self):
        assert network_types["secureConnect"] is SecureConnectAddress

    def test_bytes(self):
        addr = SecureConnectAddress(xtob("010203040506"))
        assert addr.addrAddr == xtob("010203040506")
        assert addr.addrLen == 6
        assert addr.addrNetworkType == "secureConnect"
        assert addr.addrType == Address.localStationAddr

    def test_hex_string(self):
        addr = SecureConnectAddress("0x010203040506")
        assert addr.addrAddr == xtob("010203040506")

    def test_via_address_factory(self):
        addr = Address(xtob("010203040506"), network_type="secureConnect")
        assert isinstance(addr, SecureConnectAddress)
        assert addr.addrAddr == xtob("010203040506")

    def test_local_broadcast(self):
        addr = SecureConnectAddress(SecureConnectAddress.local_broadcast)
        assert addr.addrType == Address.localBroadcastAddr
        assert addr.is_localbroadcast

    def test_wrong_length(self):
        with self.assertRaises(ValueError):
            SecureConnectAddress(xtob("0102030405"))
        with self.assertRaises(ValueError):
            SecureConnectAddress(xtob("01020304050607"))

    def test_random_48(self):
        for _ in range(50):
            addr = SecureConnectAddress.random()
            assert addr.addrLen == 6
            # low nibble of the first octet is 0x2
            assert (addr.addrAddr[0] & 0x0F) == 0x02
            assert addr.addrType == Address.localStationAddr


if __name__ == "__main__":
    unittest.main()
