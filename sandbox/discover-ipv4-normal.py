"""
Simple console example that sends Who-Is requests.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.pdu import Address, IPv4Address
from bacpypes3.comm import bind

from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.basetypes import PropertyIdentifier

from bacpypes3.ipv4.app import NormalApplication
from bacpypes3.apdu import ErrorRejectAbortNack

from bacpypes3.local.device import DeviceObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
this_application: NormalApplication = None


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Simple console example that sends Who-Is requests.
    """

    _debug: Callable[..., None]

    async def do_whois(
        self,
        address: Address = None,
        low_limit: int = None,
        high_limit: int = None,
    ) -> None:
        """
        Send a Who-Is request and wait for the responses.

        usage: whois [ address:Address [ low_limit:int high_limit:int ] ]
        """
        if _debug:
            SampleCmd._debug("do_whois %r %r %r", address, low_limit, high_limit)

        i_ams = await this_application.who_is(low_limit, high_limit, address)
        if not i_ams:
            await self.response(f"No responses")
        else:
            for i_am in i_ams:
                if _debug:
                    SampleCmd._debug("    - i_am: %r", i_am)
                await self.response(f"{i_am.iAmDeviceIdentifier[1]} {i_am.pduSource}")


def main() -> None:
    global this_application

    try:
        loop = console = cmd = this_application = None
        parser = ArgumentParser()
        parser.add_argument(
            "address",
            type=str,
            help="address",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # get the event loop
        loop = asyncio.get_event_loop()

        # evaluate the address
        ipv4_address = IPv4Address(args.address)
        if _debug:
            _log.debug("ipv4_address: %r", ipv4_address)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # make a device object
        this_device = DeviceObject(
            objectIdentifier=("device", 999),
            objectName=__file__,
            maxApduLengthAccepted=1024,
            segmentationSupported="segmentedBoth",
            maxSegmentsAccepted=64,
            vendorIdentifier=999,
        )
        if _debug:
            _log.debug("this_device: %r", this_device)

        # build the application
        this_application = NormalApplication(this_device, ipv4_address)

        # run until the console is done, canceled or EOF
        loop.run_until_complete(console.fini.wait())

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if this_application:
            this_application.server.close()
        if loop:
            loop.close()
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    main()
