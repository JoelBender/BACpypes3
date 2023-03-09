#!/usr/bin/python

"""
Simple console example that echos websocket messages, upper cased.
"""

import asyncio
import logging

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser

from bacpypes3.comm import Client, bind
from bacpypes3.pdu import PDU
from bacpypes3.sc.service import SCNodeSwitch


# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class Echo(Client[PDU]):
    """
    Echo
    """

    _debug: Callable[..., None]

    async def confirmation(self, pdu: PDU) -> None:
        if _debug:
            Echo._debug("confirmation %r", pdu)

        ack = PDU(pdu.pduData.upper(), destination=pdu.pduSource)
        if _debug:
            Echo._debug("    - ack: %r", ack)

        await self.request(ack)


async def main() -> None:
    switch = None

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

        # build a very small stack
        echo = Echo()
        switch = SCNodeSwitch(
            host=args.host, port=args.port, dc_support=True, hub_support=True
        )
        bind(echo, switch)

        # run a really long time
        await asyncio.Future()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if switch:
            await switch.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
