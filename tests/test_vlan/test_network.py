#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Network
------------

This module tests the basic functionality of a VLAN network.  Each test "runs"
on a VLAN with two nodes, node_1 and node_2, and each has a state machine.
"""

import asyncio
import pytest

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger

from bacpypes3.pdu import PDU
from bacpypes3.comm import bind
from bacpypes3.vlan import Network, Node

from ..state_machine import ClientStateMachine, StateMachineGroup

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class TNetwork(StateMachineGroup):
    def __init__(self, clocked_test, node_count):  # noqa: F811
        if _debug:
            TNetwork._debug("__init__ %r", node_count)
        StateMachineGroup.__init__(self)

        self.vlan = Network(broadcast_address=0)
        self.clocked_test = clocked_test

        for i in range(node_count):
            node = Node(i + 1, self.vlan)

            # bind a client state machine to the node
            csm = ClientStateMachine(name=f"node {i + 1}")
            bind(csm, node)

            # add it to this group
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
class TestVLAN:
    @pytest.mark.asyncio
    async def test_idle(self, clocked_test):
        """Test that a very quiet network can exist.  This is not a network
        test so much as a state machine group test.
        """
        if _debug:
            TestVLAN._debug("test_idle")

        # two element network
        tnet = TNetwork(clocked_test, 2)
        tnode1, tnode2 = tnet.state_machines

        # set the start states of both machines to success
        tnode1.start_state.success()
        tnode2.start_state.success()

        # run the group
        await tnet.run()

    @pytest.mark.asyncio
    async def test_send_receive(self, clocked_test):
        """Test that a node can send a message to another node."""
        if _debug:
            TestVLAN._debug("test_send_receive")

        # two element network
        tnet = TNetwork(clocked_test, 2)
        tnode1, tnode2 = tnet.state_machines

        # make a PDU from node 1 to node 2
        pdu = PDU(b"data", source=1, destination=2)
        if _debug:
            TestVLAN._debug("    - pdu: %r", pdu)

        # node 1 sends the pdu, mode 2 gets it
        tnode1.start_state.send(pdu).success()
        tnode2.start_state.receive(PDU, pduSource=1).success()

        # run the group
        await tnet.run()

    @pytest.mark.asyncio
    async def test_broadcast(self, clocked_test):
        """Test that a node can send out a 'local broadcast' message which will
        be received by every other node.
        """
        if _debug:
            TestVLAN._debug("test_broadcast")

        # three element network
        tnet = TNetwork(clocked_test, 3)
        tnode1, tnode2, tnode3 = tnet.state_machines

        # make a broadcast PDU
        pdu = PDU(b"data", source=1, destination=0)
        if _debug:
            TestVLAN._debug("    - pdu: %r", pdu)

        # node 1 sends the pdu, node 2 and 3 each get it
        tnode1.start_state.send(pdu).success()
        tnode2.start_state.receive(PDU, pduSource=1).success()
        tnode3.start_state.receive(PDU, pduSource=1).success()

        # run the group
        await tnet.run()

    @pytest.mark.asyncio
    async def test_spoof_fail(self, clocked_test):
        """Test verifying that a node cannot send out packets with a source
        address other than its own, see also test_spoof_pass().
        """
        if _debug:
            TestVLAN._debug("test_spoof_fail")

        # two element network
        tnet = TNetwork(clocked_test, 1)
        (tnode1,) = tnet.state_machines

        # make a unicast PDU with the wrong source
        pdu = PDU(b"data", source=2, destination=3)

        # the node sends the pdu and would be a success but...
        tnode1.start_state.send(pdu).success()

        # when the node attempts to send it raises an error
        with pytest.raises(RuntimeError):
            await tnet.run()

    @pytest.mark.asyncio
    async def test_spoof_pass(self, clocked_test):
        """Test allowing a node to send out packets with a source address
        other than its own, see also test_spoof_fail().
        """
        if _debug:
            TestVLAN._debug("test_spoof_pass")

        # one node network
        tnet = TNetwork(clocked_test, 1)
        (tnode1,) = tnet.state_machines

        # reach into the network and enable spoofing for the node
        tnet.vlan.nodes[0].spoofing = True

        # make a unicast PDU from a fictitious node
        pdu = PDU(b"data", source=3, destination=1)

        # node 1 sends the pdu, but gets it back as if it was from node 3
        tnode1.start_state.send(pdu).receive(PDU, pduSource=3).success()

        # run the group
        await tnet.run()

    @pytest.mark.asyncio
    async def test_promiscuous_pass(self, clocked_test):
        """Test 'promiscuous mode' of a node which allows it to receive every
        packet sent on the network.  This is like the network is a hub, or
        the node is connected to a 'monitor' port on a managed switch.
        """
        if _debug:
            TestVLAN._debug("test_promiscuous_pass")

        # three element network
        tnet = TNetwork(clocked_test, 3)
        tnode1, tnode2, tnode3 = tnet.state_machines

        # reach into the network and enable promiscuous mode
        tnet.vlan.nodes[2].promiscuous = True

        # make a PDU from node 1 to node 2
        pdu = PDU(b"data", source=1, destination=2)

        # node 1 sends the pdu to node 2, node 3 also gets a copy
        tnode1.start_state.send(pdu).success()
        tnode2.start_state.receive(PDU, pduSource=1).success()
        tnode3.start_state.receive(PDU, pduDestination=2).success()

        # run the group
        await tnet.run()

    @pytest.mark.asyncio
    async def test_promiscuous_fail(self, clocked_test):
        if _debug:
            TestVLAN._debug("test_promiscuous_fail")

        # three element network
        tnet = TNetwork(clocked_test, 3)
        tnode1, tnode2, tnode3 = tnet.state_machines

        # make a PDU from node 1 to node 2
        pdu = PDU(b"data", source=1, destination=2)

        # node 1 sends the pdu to node 2, node 3 waits and gets nothing
        tnode1.start_state.send(pdu).success()
        tnode2.start_state.receive(PDU, pduSource=1).success()

        # if node 3 receives anything it will trigger unexpected receive and fail
        tnode3.start_state.timeout(0.5).success()

        # run the group
        await tnet.run()


@bacpypes_debugging
class TestVLANEvents:
    @pytest.mark.asyncio
    async def test_send_receive(self, clocked_test):
        """Test that a node can send a message to another node and use
        events to continue with the messages.
        """
        if _debug:
            TestVLAN._debug("test_send_receive")

        # two element network
        tnet = TNetwork(clocked_test, 2)
        tnode1, tnode2 = tnet.state_machines

        # make a PDU from node 1 to node 2
        dead_pdu = PDU(b"dead", source=1, destination=2)
        if _debug:
            TestVLAN._debug("    - dead_pdu: %r", dead_pdu)

        # make a PDU from node 1 to node 2
        beef_pdu = PDU(b"beef", source=1, destination=2)
        if _debug:
            TestVLAN._debug("    - beef_pdu: %r", beef_pdu)

        # node 1 sends dead_pdu, waits for event, sends beef_pdu
        tnode1.start_state.send(dead_pdu).wait_event("e").send(beef_pdu).success()

        # node 2 receives dead_pdu, sets event, waits for beef_pdu
        tnode2.start_state.receive(PDU, pduData=b"dead").set_event("e").receive(
            PDU, pduData=b"beef"
        ).success()

        # run the group
        await tnet.run()
