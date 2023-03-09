#!/usr/bin/python

"""
Simple console example that sends websocket messages.
"""

import sys
import asyncio
import logging

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.comm import Client, bind
from bacpypes3.pdu import PDU
from bacpypes3.sc.service import SCNodeSwitch

# some debugging
_debug = 0
_log = ModuleLogger(globals())

direct_connection = None


@bacpypes_debugging
class SampleCmd(Cmd, Client[PDU]):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_send(self, data: str) -> None:
        """
        usage: send data:str
        """
        if _debug:
            SampleCmd._debug("do_send %r", data)
        global direct_connection

        pdu = PDU(data.encode(), destination=direct_connection)
        if _debug:
            SampleCmd._debug("    - pdu: %r", pdu)

        await self.request(pdu)

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            SampleCmd._debug("confirmation %r", pdu)

        await self.response(pdu.pduData.decode())


async def main() -> None:
    global direct_connection

    switch = None
    console = None
    try:
        parser = ArgumentParser()
        parser.add_argument(
            "--host",
            type=str,
            default="localhost",
            help="listening host address",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8765,
            help="listening port",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("settings: %r", settings)
            _log.debug("args: %r", args)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        switch = SCNodeSwitch()
        bind(console, cmd, switch)  # type: ignore[misc]

        # establish a direct connection
        direct_connection = switch.connect_to_device(f"ws://{args.host}:{args.port}")
        if _debug:
            _log.debug("direct_connection: %r", direct_connection)

        # run until the console is done, canceled or EOF
        await console.fini.wait()
        _log.debug("console fini")

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if direct_connection:
            _log.debug("direct_connection.close()")
            await direct_connection.close()
        if switch:
            _log.debug("switch.close()")
            await switch.close()
        if console and console.exit_status:
            _log.debug("sys.exit()")
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
