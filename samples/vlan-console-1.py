#!/usr/bin/python

"""
This application creates a VLAN with a set of nodes.  The console can send
data to a specific node or broadcast to all the nodes.

Note that address zero (0) is the local broadcast address.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.pdu import PDU
from bacpypes3.comm import Client, bind
from bacpypes3.vlan import Network, Node

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class Print(Client[PDU]):
    """
    Print the PDU received.
    """

    _debug: Callable[..., None]

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            SampleCmd._debug("confirmation %r", pdu)

        print(str(pdu))


@bacpypes_debugging
class Uppercase(Client[PDU]):
    """
    Return a PDU with the contents uppercase.  This function simulates taking
    a while by calling asyncio.sleep().
    """

    _debug: Callable[..., None]

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            Uppercase._debug("confirmation %r", pdu)

        # decode the bytearrary as a character string
        pdu_str: str = pdu.pduData.decode()
        if _debug:
            Uppercase._debug("    - request: %r", pdu_str)

        # wait a bit
        await asyncio.sleep(2.0)

        # uppercase it and return it
        pdu = PDU(pdu_str.upper().encode(), destination=pdu.pduSource)
        if _debug:
            Uppercase._debug("    - pdu: %r", pdu)

        await self.request(pdu)


@bacpypes_debugging
class SampleCmd(Cmd, Client[PDU]):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_send(self, address: int, data: str) -> None:
        """
        usage: send address:int data:str
        """
        if _debug:
            SampleCmd._debug("do_send %r %r", address, data)

        pdu = PDU(data.encode(), destination=address)
        if _debug:
            SampleCmd._debug("    - pdu: %r", pdu)

        await self.request(pdu)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            SampleCmd._debug("confirmation %r", pdu)

        await self.response(str(pdu))


@bacpypes_debugging
class TestNet(Network[int]):
    _debug: Callable[..., None]

    def __init__(self) -> None:
        if _debug:
            TestNet._debug("__init__")
        super().__init__(broadcast_address=0)


@bacpypes_debugging
class TestNode(Node[int]):
    _debug: Callable[..., None]

    def __init__(self, address: int, lan: TestNet) -> None:
        if _debug:
            TestNode._debug("__init__ %r %r", address, lan)
        super().__init__(address, lan)

    async def indication(self, pdu: PDU) -> None:
        if _debug:
            TestNode._debug("indication %r", pdu)

        await super().indication(pdu)

    async def response(self, pdu: PDU) -> None:
        if _debug:
            TestNode._debug("response %r", pdu)

        await super().response(pdu)


async def main() -> None:
    try:
        console = None
        ArgumentParser().parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # make a network
        net = TestNet()
        if _debug:
            _log.debug("net: %r", net)

        # build a very small stack on a test node, address 1
        node1 = TestNode(address=1, lan=net)
        if _debug:
            _log.debug("node1: %r", node1)

        console = Console()
        cmd = SampleCmd()
        bind(console, cmd, node1)  # type: ignore[misc]

        # make another node that just prints what it gets
        node2 = TestNode(address=2, lan=net)
        if _debug:
            _log.debug("node2: %r", node2)
        bind(Print(), node2)

        # make another node that returns the strings it gets uppercased
        node3 = TestNode(address=3, lan=net)
        if _debug:
            _log.debug("node3: %r", node3)
        bind(Uppercase(), node3)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    finally:
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
