#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test IP4 Router
---------------

This module tests the basic functionality of an IPv4 VLAN router.
"""

import asyncio
import ipaddress
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

from bacpypes3.pdu import Address, PDU
from bacpypes3.comm import bind
from bacpypes3.vlan import IPv4Network, IPv4Node, IPv4Router

from ..state_machine import ClientStateMachine, StateMachineGroup

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class TNetwork(StateMachineGroup):
    def __init__(self, clocked_test):
        if _debug:
            TNetwork._debug("__init__")
        super().__init__()

        self.clocked_test = clocked_test

        # make a router and add the networks
        trouter = IPv4Router()

        # add nodes to the networks
        for pattern in ("192.168.10.{}/24", "192.168.20.{}/24"):

            # make the network
            vlan = IPv4Network(ipaddress.IPv4Network(pattern.format(0)))

            # add the network to the router
            trouter.add_network(Address(pattern.format(1)), vlan)

            for i in range(2):
                address = pattern.format(i + 2)
                node = IPv4Node(Address(address), vlan)
                if _debug:
                    TNetwork._debug("    - node: %r", node)

                # bind a client state machine to the node
                csm = ClientStateMachine(name=address)
                if _debug:
                    TNetwork._debug("    - csm: %r", csm)

                bind(csm, node)

                # handy to have the state machine know the address of its node
                csm.address = node.address

                # add it to the group
                self.append(csm)

    async def run(self, time_limit=60.0):
        if _debug:
            TNetwork._debug("run %r", time_limit)

        # run the group
        await super().run()

        if _debug:
            TNetwork._debug("    - loop: %r", self.clocked_test.loop)
            TNetwork._debug(
                "    - advancing: %r + %r", self.clocked_test.loop.time(), time_limit
            )

            all_tasks = asyncio.all_tasks(self.clocked_test.loop)
            TNetwork._debug("    - all_tasks: %r", all_tasks)

        await self.clocked_test.advance(time_limit)

        if _debug:
            TNetwork._debug("    - advanced: %r", self.clocked_test.loop.time())

            all_tasks = asyncio.all_tasks(self.clocked_test.loop)
            TNetwork._debug("    - all_tasks: %r", all_tasks)

        # check for success
        all_success, some_failed = super().check_for_success()
        if _debug:
            TNetwork._debug(
                "    - all_success, some_failed: %r, %r", all_success, some_failed
            )

        assert all_success


@bacpypes_debugging
class TestIPv4Router:
    @pytest.mark.asyncio
    async def test_send_receive(self, clocked_test):
        """Test that a node can send a message to another node on
        a different network.
        """
        if _debug:
            TestIPv4Router._debug("test_send_receive")

        # build the network
        tnet = TNetwork(clocked_test)

        # unpack the state machines
        csm_10_2, csm_10_3, csm_20_2, csm_20_3 = tnet.state_machines

        # make a PDU from network 10 node 1 to network 20 node 2
        pdu = PDU(
            b"data",
            source=csm_10_2.address,
            destination=csm_20_3.address,
        )
        if _debug:
            TestIPv4Router._debug("    - pdu: %r", pdu)

        # node 1 sends the pdu, mode 2 gets it
        csm_10_2.start_state.send(pdu).success()
        csm_20_3.start_state.receive(
            PDU,
            pduSource=csm_10_2.address,
        ).success()

        # other nodes get nothing
        csm_10_3.start_state.timeout(1).success()
        csm_20_2.start_state.timeout(1).success()

        # run the group
        await tnet.run()

    @pytest.mark.asyncio
    async def test_local_broadcast(self, clocked_test):
        """Test that a node can send a message to all of the other nodes on
        the same network.
        """
        if _debug:
            TestIPv4Router._debug("test_local_broadcast")

        # build the network
        tnet = TNetwork(clocked_test)

        # unpack the state machines
        csm_10_2, csm_10_3, csm_20_2, csm_20_3 = tnet.state_machines

        # make a broadcast PDU from network 10 node 1
        pdu = PDU(
            b"data",
            source=csm_10_2.address,
            destination=Address("192.168.10.255"),
        )
        if _debug:
            TestIPv4Router._debug("    - pdu: %r", pdu)

        # node 10-2 sends the pdu, node 10-3 gets pdu, nodes 20-2 and 20-3 dont
        csm_10_2.start_state.send(pdu).success()
        csm_10_3.start_state.receive(
            PDU,
            pduSource=csm_10_2.address,
        ).success()
        csm_20_2.start_state.timeout(1).success()
        csm_20_3.start_state.timeout(1).success()

        # run the group
        await tnet.run()

    @pytest.mark.asyncio
    async def test_remote_broadcast(self, clocked_test):
        """Test that a node can send a message to all of the other nodes on
        a different network.
        """
        if _debug:
            TestIPv4Router._debug("test_remote_broadcast")

        # build the network
        tnet = TNetwork(clocked_test)

        # unpack the state machines
        csm_10_2, csm_10_3, csm_20_2, csm_20_3 = tnet.state_machines

        # make a PDU from network 10 node 1 to network 20 node 2
        pdu = PDU(
            b"data",
            source=csm_10_2.address,
            destination=Address("192.168.20.255"),
        )
        if _debug:
            TestIPv4Router._debug("    - pdu: %r", pdu)

        # node 10-2 sends the pdu, node 10-3 gets nothing, nodes 20-2 and 20-3 get it
        csm_10_2.start_state.send(pdu).success()
        csm_10_3.start_state.timeout(1).success()
        csm_20_2.start_state.receive(
            PDU,
            pduSource=csm_10_2.address,
        ).success()
        csm_20_3.start_state.receive(
            PDU,
            pduSource=csm_10_2.address,
        ).success()

        # run the group
        await tnet.run()
