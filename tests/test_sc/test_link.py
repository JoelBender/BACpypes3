#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test BACnet/SC node link layer
------------------------------
"""

import unittest
from uuid import uuid4

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.pdu import SecureConnectAddress
from bacpypes3.sc.link import SCNodeLinkLayer
from bacpypes3.sc.service import SCBVLLServiceAccessPoint, SCHubConnector
from bacpypes3.sc.bvll import BVLLCodec

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class TestSCNodeLinkLayer(unittest.TestCase):
    _debug = None  # type: ignore[assignment]

    def make(self):
        vmac = SecureConnectAddress.random()
        return SCNodeLinkLayer(vmac, uuid4(), "wss://hub.example.org/"), vmac

    def test_is_bvll_entity(self):
        link_layer, vmac = self.make()
        assert isinstance(link_layer, SCBVLLServiceAccessPoint)
        assert link_layer.local_vmac is vmac

    def test_stack_wiring(self):
        link_layer, vmac = self.make()
        assert isinstance(link_layer.codec, BVLLCodec)
        assert isinstance(link_layer.connector, SCHubConnector)

        # entity -> codec -> connector
        assert link_layer.clientPeer is link_layer.codec
        assert link_layer.codec.serverPeer is link_layer
        assert link_layer.codec.clientPeer is link_layer.connector
        assert link_layer.connector.serverPeer is link_layer.codec

    def test_failover_uri(self):
        vmac = SecureConnectAddress.random()
        link_layer = SCNodeLinkLayer(vmac, uuid4(), "wss://primary/", "wss://failover/")
        assert link_layer.connector._uris == ["wss://primary/", "wss://failover/"]

    def test_vmac_change_propagates(self):
        link_layer, vmac = self.make()
        new_vmac = SecureConnectAddress.random()

        # simulate the connector regenerating its VMAC after a collision
        link_layer.connector.vmac = new_vmac
        link_layer._vmac_changed(new_vmac)
        assert link_layer.local_vmac is new_vmac


if __name__ == "__main__":
    unittest.main()
