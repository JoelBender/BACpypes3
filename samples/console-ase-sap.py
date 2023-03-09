#!/usr/bin/python

"""
Simple console example that forwards the input to a service and echos the
response.  The service converts the requests to uppercase.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console, ConsolePDU
from bacpypes3.comm import Server, ApplicationServiceElement, ServiceAccessPoint, bind

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class Echo(Server[ConsolePDU], ApplicationServiceElement):
    """
    Simple example server that echos the downstream strings as uppercase
    strings going upstream.  If the PDU is None the console is finished,
    and this could send an integer status code upstream to exit.
    """

    _debug: Callable[..., None]

    async def indication(self, pdu: ConsolePDU) -> None:
        if _debug:
            Echo._debug("indication {!r}".format(pdu))
        if pdu is None:
            return

        await self.request(pdu)

    async def confirmation(self, pdu: ConsolePDU) -> None:
        if _debug:
            Echo._debug("confirmation {!r}".format(pdu))
        if pdu is None:
            return

        await self.response(pdu.upper())


@bacpypes_debugging
class EchoServiceAccessPoint(ServiceAccessPoint):

    _debug: Callable[..., None]

    async def sap_indication(self, pdu: str) -> None:
        if _debug:
            EchoServiceAccessPoint._debug("sap_indication {!r}".format(pdu))
        await self.sap_response(pdu.upper())


async def main() -> None:
    try:
        console = None
        ArgumentParser().parse_args()

        # build a very small stack
        console = Console()
        echo = Echo()
        echo_service = EchoServiceAccessPoint()
        bind(console, echo, echo_service)  # type: ignore[misc]

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
