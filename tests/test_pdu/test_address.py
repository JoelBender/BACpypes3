#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test PDU Address
----------------
"""

import unittest
import pytest

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger, xtob
from bacpypes3.pdu import (
    Address,
    LocalStation,
    RemoteStation,
    LocalBroadcast,
    RemoteBroadcast,
    GlobalBroadcast,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class MatchAddressMixin:
    def match_address(self, addr, addrType, addrNet, addrLen, addrAddr):
        """Assert that the type, network, length, and address are what
        they should be.  Note that the address parameter is a hex string
        that will be converted to bytes for comparison.

        :param addr: the address to match
        :param addrType: the address type
        :param addrNet: the network number
        :param addrLen: the address length
        :param addrAddr: the address expressed as hex bytes
        """
        if _debug:
            MatchAddressMixin._debug(
                "match_address %r %r %r %r %r",
                addr,
                addrType,
                addrNet,
                addrLen,
                addrAddr,
            )

        assert addr.addrType == addrType
        assert addr.addrNet == addrNet
        assert addr.addrLen == addrLen
        if addrAddr is None:
            assert addr.addrAddr is None
        else:
            assert addr.addrAddr == xtob(addrAddr)


@bacpypes_debugging
class TestAddress(unittest.TestCase, MatchAddressMixin):
    def test_address(self):
        if _debug:
            TestAddress._debug("test_address")

        # null address
        test_addr = Address()
        self.match_address(test_addr, 0, None, None, None)
        assert str(test_addr) == "Null"

    def test_address_int(self):
        if _debug:
            TestAddress._debug("test_address_int")

        # test integer local station
        test_addr = Address(1)
        self.match_address(test_addr, 2, None, 1, "01")
        assert str(test_addr) == "1"

        test_addr = Address(254)
        self.match_address(test_addr, 2, None, 1, "fe")
        assert str(test_addr) == "254"

        # test bad integer
        with pytest.raises(ValueError):
            Address(-1)
        with pytest.raises(ValueError):
            Address(256)

    def test_address_ipv4_str(self):
        if _debug:
            TestAddress._debug("test_address_ipv4_str")

        # test IPv4 local station address
        test_addr = Address("1.2.3.4")
        self.match_address(test_addr, 2, None, 6, "01020304BAC0")
        assert str(test_addr) == "1.2.3.4"

        # test IPv4 local station address with non-standard port
        test_addr = Address("1.2.3.4:47809")
        self.match_address(test_addr, 2, None, 6, "01020304BAC1")
        assert str(test_addr) == "1.2.3.4:47809"

        # test IPv4 local station address with unrecognized port
        test_addr = Address("1.2.3.4:47999")
        self.match_address(test_addr, 2, None, 6, "01020304bb7f")
        assert str(test_addr) == "1.2.3.4:47999"

        # test IPv4 local station network size address
        test_addr = Address("1.2.3.4/24")
        self.match_address(test_addr, 2, None, 6, "01020304BAC0")
        assert str(test_addr) == "1.2.3.4"
        assert test_addr.addrBroadcastTuple == ("1.2.3.255", 47808)

        # test IPv4 local station network mask address
        test_addr = Address("1.2.3.4/255.255.255.0")
        self.match_address(test_addr, 2, None, 6, "01020304BAC0")
        assert str(test_addr) == "1.2.3.4"
        assert test_addr.addrBroadcastTuple == ("1.2.3.255", 47808)

    def test_address_eth_str(self):
        if _debug:
            TestAddress._debug("test_address_eth_str")

        # test Ethernet local station address
        test_addr = Address("01:02:03:04:05:06")
        self.match_address(test_addr, 2, None, 6, "010203040506")
        assert str(test_addr) == "01:02:03:04:05:06"

    def test_address_local_station_str(self):
        if _debug:
            TestAddress._debug("test_address_local_station_str")

        # test integer local station
        test_addr = Address("1")
        self.match_address(test_addr, 2, None, 1, "01")
        assert str(test_addr) == "1"

        test_addr = Address("254")
        self.match_address(test_addr, 2, None, 1, "fe")
        assert str(test_addr) == "254"

        # test bad integer string
        with pytest.raises(ValueError):
            Address("256")

        # test modern hex string
        test_addr = Address("0x01")
        self.match_address(test_addr, 2, None, 1, "01")
        assert str(test_addr) == "1"

        test_addr = Address("0x0102")
        self.match_address(test_addr, 2, None, 2, "0102")
        assert str(test_addr) == "0x0102"

        # test old school hex string
        if False:
            test_addr = Address("X'01'")
            self.match_address(test_addr, 2, None, 1, "01")
            assert str(test_addr) == "1"

            test_addr = Address("X'0102'")
            self.match_address(test_addr, 2, None, 2, "0102")
            assert str(test_addr) == "0x0102"

    def test_address_local_broadcast_str(self):
        if _debug:
            TestAddress._debug("test_address_local_broadcast_str")

        # test local broadcast
        test_addr = Address("*")
        self.match_address(test_addr, 1, None, None, None)
        assert str(test_addr) == "*"

    def test_address_remote_broadcast_str(self):
        if _debug:
            TestAddress._debug("test_address_remote_broadcast_str")

        # test remote broadcast
        test_addr = Address("1:*")
        self.match_address(test_addr, 3, 1, None, None)
        assert str(test_addr) == "1:*"

        # test remote broadcast bad network
        with pytest.raises(ValueError):
            Address("65536:*")

    def test_address_remote_station_str(self):
        if _debug:
            TestAddress._debug("test_address_remote_station_str")

        # test integer remote station
        test_addr = Address("1:2")
        self.match_address(test_addr, 4, 1, 1, "02")
        assert str(test_addr) == "1:2"

        test_addr = Address("1:254")
        self.match_address(test_addr, 4, 1, 1, "fe")
        assert str(test_addr) == "1:254"

        # test bad network and node
        with pytest.raises(ValueError):
            Address("65536:2")
        with pytest.raises(ValueError):
            Address("1:256")

        # test modern hex string
        test_addr = Address("1:0x02")
        self.match_address(test_addr, 4, 1, 1, "02")
        assert str(test_addr) == "1:2"

        # test bad network
        with pytest.raises(ValueError):
            Address("65536:0x02")

        test_addr = Address("1:0x0203")
        self.match_address(test_addr, 4, 1, 2, "0203")
        assert str(test_addr) == "1:0x0203"

        # test old school hex string
        if False:
            test_addr = Address("1:X'02'")
            self.match_address(test_addr, 4, 1, 1, "02")
            assert str(test_addr) == "1:2"

            test_addr = Address("1:X'0203'")
            self.match_address(test_addr, 4, 1, 2, "0203")
            assert str(test_addr) == "1:0x0203"

            # test bad network
            with pytest.raises(ValueError):
                Address("65536:X'02'")

    def test_address_global_broadcast_str(self):
        if _debug:
            TestAddress._debug("test_address_global_broadcast_str")

        # test local broadcast
        test_addr = Address("*:*")
        self.match_address(test_addr, 5, None, None, None)
        assert str(test_addr) == "*:*"


@bacpypes_debugging
class TestLocalStation(unittest.TestCase, MatchAddressMixin):
    def test_local_station(self):
        if _debug:
            TestLocalStation._debug("test_local_station")

        # one parameter
        with pytest.raises(TypeError):
            LocalStation()

        # test integer
        test_addr = LocalStation(1)
        self.match_address(test_addr, 2, None, 1, "01")
        assert str(test_addr) == "1"

        test_addr = LocalStation(254)
        self.match_address(test_addr, 2, None, 1, "fe")
        assert str(test_addr) == "254"

        # test bad integer
        with pytest.raises(ValueError):
            LocalStation(-1)
        with pytest.raises(ValueError):
            LocalStation(256)

        # test bytes
        test_addr = LocalStation(xtob("01"))
        self.match_address(test_addr, 2, None, 1, "01")
        assert str(test_addr) == "1"

        test_addr = LocalStation(xtob("fe"))
        self.match_address(test_addr, 2, None, 1, "fe")
        assert str(test_addr) == "254"

        # multi-byte strings are hex encoded
        test_addr = LocalStation(xtob("0102"))
        self.match_address(test_addr, 2, None, 2, "0102")
        assert str(test_addr) == "0x0102"

        test_addr = LocalStation(xtob("010203"))
        self.match_address(test_addr, 2, None, 3, "010203")
        assert str(test_addr) == "0x010203"


@bacpypes_debugging
class TestRemoteStation(unittest.TestCase, MatchAddressMixin):
    def test_remote_station(self):
        if _debug:
            TestRemoteStation._debug("test_remote_station")

        # two parameters, correct types
        with pytest.raises(TypeError):
            RemoteStation()
        with pytest.raises(TypeError):
            RemoteStation("x", 2)

        # test bad network
        with pytest.raises(ValueError):
            RemoteStation(-1, 1)
        with pytest.raises(ValueError):
            RemoteStation(65536, 1)

    def test_remote_station_ints(self):
        if _debug:
            TestRemoteStation._debug("test_remote_station_ints")

        # test integer
        test_addr = RemoteStation(1, 1)
        self.match_address(test_addr, 4, 1, 1, "01")
        assert str(test_addr) == "1:1"

        test_addr = RemoteStation(1, 254)
        self.match_address(test_addr, 4, 1, 1, "fe")
        assert str(test_addr) == "1:254"

        # test station address
        with pytest.raises(ValueError):
            RemoteStation(1, -1)
        with pytest.raises(ValueError):
            RemoteStation(1, 256)

    def test_remote_station_bytes(self):
        if _debug:
            TestRemoteStation._debug("test_remote_station_bytes")

        # multi-byte strings are hex encoded
        test_addr = RemoteStation(1, xtob("0102"))
        self.match_address(test_addr, 4, 1, 2, "0102")
        assert str(test_addr) == "1:0x0102"

        test_addr = RemoteStation(1, xtob("010203"))
        self.match_address(test_addr, 4, 1, 3, "010203")
        assert str(test_addr) == "1:0x010203"

        # match with an IPv4 address
        test_addr = RemoteStation(1, xtob("01020304bac0"))
        self.match_address(test_addr, 4, 1, 6, "01020304bac0")
        assert str(test_addr) == "1:1.2.3.4"

    def test_remote_station_ints_routed(self):
        if _debug:
            TestRemoteStation._debug("test_remote_station_ints_routed")

        if not settings.route_aware:
            if _debug:
                TestRemoteStation._debug("    - not route aware")
            return

        # test integer
        test_addr = RemoteStation(1, 1, route=Address("1.2.3.4"))
        self.match_address(test_addr, 4, 1, 1, "01")
        assert str(test_addr) == "1:1@1.2.3.4"

        test_addr = RemoteStation(1, 254, route=Address("1.2.3.4"))
        self.match_address(test_addr, 4, 1, 1, "fe")
        assert str(test_addr) == "1:254@1.2.3.4"

        # test station address
        with pytest.raises(ValueError):
            RemoteStation(1, -1)
        with pytest.raises(ValueError):
            RemoteStation(1, 256)

    def test_remote_station_bytes_routed(self):
        if _debug:
            TestRemoteStation._debug("test_remote_station_bytes_routed")

        if not settings.route_aware:
            if _debug:
                TestRemoteStation._debug("    - not route aware")
            return

        # multi-byte strings are hex encoded
        test_addr = RemoteStation(1, xtob("0102"), route=Address("1.2.3.4"))
        self.match_address(test_addr, 4, 1, 2, "0102")
        assert str(test_addr) == "1:0x0102@1.2.3.4"

        test_addr = RemoteStation(1, xtob("010203"), route=Address("1.2.3.4"))
        self.match_address(test_addr, 4, 1, 3, "010203")
        assert str(test_addr) == "1:0x010203@1.2.3.4"

        # match with an IPv4 address
        test_addr = RemoteStation(1, xtob("01020304bac0"), route=Address("1.2.3.4"))
        self.match_address(test_addr, 4, 1, 6, "01020304bac0")
        assert str(test_addr) == "1:1.2.3.4@1.2.3.4"


@bacpypes_debugging
class TestLocalBroadcast(unittest.TestCase, MatchAddressMixin):
    def test_local_broadcast(self):
        if _debug:
            TestLocalBroadcast._debug("test_local_broadcast")

        test_addr = LocalBroadcast()
        self.match_address(test_addr, 1, None, None, None)
        assert str(test_addr) == "*"

    def test_local_broadcast_routed(self):
        if _debug:
            TestLocalBroadcast._debug("test_local_broadcast_routed")

        if not settings.route_aware:
            if _debug:
                TestLocalBroadcast._debug("    - not route aware")
            return

        test_addr = LocalBroadcast(route=Address("1.2.3.4"))
        self.match_address(test_addr, 1, None, None, None)
        assert str(test_addr) == "*@1.2.3.4"


@bacpypes_debugging
class TestRemoteBroadcast(unittest.TestCase, MatchAddressMixin):
    def test_remote_broadcast(self):
        if _debug:
            TestRemoteBroadcast._debug("test_remote_broadcast")

        # one parameter, correct type
        with pytest.raises(TypeError):
            RemoteBroadcast()
        with pytest.raises(TypeError):
            RemoteBroadcast("x")

        # test bad network
        with pytest.raises(ValueError):
            RemoteBroadcast(-1)
        with pytest.raises(ValueError):
            RemoteBroadcast(65536)

        # match
        test_addr = RemoteBroadcast(1)
        self.match_address(test_addr, 3, 1, None, None)
        assert str(test_addr) == "1:*"

    def test_remote_broadcast_routed(self):
        if _debug:
            TestRemoteBroadcast._debug("test_remote_broadcast_routed")

        if not settings.route_aware:
            if _debug:
                TestRemoteBroadcast._debug("    - not route aware")
            return

        # match
        test_addr = RemoteBroadcast(1, route=Address("1.2.3.4"))
        self.match_address(test_addr, 3, 1, None, None)
        assert str(test_addr) == "1:*@1.2.3.4"


@bacpypes_debugging
class TestGlobalBroadcast(unittest.TestCase, MatchAddressMixin):
    def test_global_broadcast(self):
        if _debug:
            TestGlobalBroadcast._debug("test_global_broadcast")

        test_addr = GlobalBroadcast()
        self.match_address(test_addr, 5, None, None, None)
        assert str(test_addr) == "*:*"

    def test_global_broadcast_routed(self):
        if _debug:
            TestGlobalBroadcast._debug("test_global_broadcast_routed")

        if not settings.route_aware:
            if _debug:
                TestGlobalBroadcast._debug("    - not route aware")
            return

        test_addr = GlobalBroadcast(route=Address("1.2.3.4"))
        self.match_address(test_addr, 5, None, None, None)
        assert str(test_addr) == "*:*@1.2.3.4"


@bacpypes_debugging
class TestAddressEquality(unittest.TestCase, MatchAddressMixin):
    def test_address_equality_str(self):
        if _debug:
            TestAddressEquality._debug("test_address_equality_str")

        assert Address(1) == LocalStation(1)
        assert Address("2") == LocalStation(2)
        assert Address("*") == LocalBroadcast()
        assert Address("3:4") == RemoteStation(3, 4)
        assert Address("5:*") == RemoteBroadcast(5)

        assert Address("*:*") == GlobalBroadcast()

    def test_address_equality_str_routed(self):
        if _debug:
            TestAddressEquality._debug("test_address_equality_str_routed")

        if not settings.route_aware:
            if _debug:
                TestAddressEquality._debug("    - not route aware")
            return

        assert Address("3:4@6.7.8.9") == RemoteStation(3, 4, route=Address("6.7.8.9"))
        assert Address("5:*@6.7.8.9") == RemoteBroadcast(5, route=Address("6.7.8.9"))
        assert Address("*:*@6.7.8.9") == GlobalBroadcast(route=Address("6.7.8.9"))
