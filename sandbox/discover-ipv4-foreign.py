"""
Simple console example of a foreign device that sends Who-Is requests.
"""

import sys
import asyncio

from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import ArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.pdu import (
    Address,
    LocalBroadcast,
    RemoteBroadcast,
    GlobalBroadcast,
    IPv4Address,
)
from bacpypes3.comm import bind

from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.basetypes import PropertyIdentifier

from bacpypes3.app import BIPForeignApplication
from bacpypes3.apdu import ErrorRejectAbortNack

from bacpypes3.local.device import DeviceObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
this_application: BIPForeignApplication = None


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

        # default to global broadcast
        address = address or GlobalBroadcast()

        # attempts to broadcast whilst unregistered will ultimately fail
        if (
            isinstance(
                address,
                (
                    LocalBroadcast,
                    RemoteBroadcast,
                    GlobalBroadcast,
                ),
            )
            and this_application.foreign.bbmdRegistrationStatus != 0
        ):
            await self.response(f"unregistered")
            return

        # pass it along to the application
        i_ams = await this_application.who_is(low_limit, high_limit, address)
        if not i_ams:
            await self.response(f"No responses")
        else:
            for i_am in i_ams:
                if _debug:
                    SampleCmd._debug("    - i_am: %r", i_am)
                await self.response(f"{i_am.iAmDeviceIdentifier[1]} {i_am.pduSource}")

    def do_register(self, address: Address, ttl: int) -> None:
        """
        usage: register address:Address ttl:int
        """
        global this_application
        if _debug:
            SampleCmd._debug("do_register %r %r", address, ttl)

        this_application.foreign.register(address, ttl)

    def do_unregister(self) -> None:
        """
        usage: unregister
        """
        global this_application
        if _debug:
            SampleCmd._debug("do_unregister")

        this_application.foreign.unregister()


def main() -> None:
    global this_application

    try:
        loop = console = cmd = this_application = None
        parser = ArgumentParser()
        parser.add_argument(
            "local_address",
            type=str,
            help="local address (e.g., 'host')",
        )
        parser.add_argument(
            "bbmd_address",
            type=str,
            help="BBMD address",
        )
        parser.add_argument(
            "ttl",
            type=int,
            help="time-to-live",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # get the event loop
        loop = asyncio.get_event_loop()

        # evaluate the address
        local_address = IPv4Address(args.local_address)
        if _debug:
            _log.debug("local_address: %r", local_address)

        # evaluate the BBMD address
        bbmd_address = IPv4Address(args.bbmd_address)
        if _debug:
            _log.debug("bbmd_address: %r", bbmd_address)
            _log.debug("args.ttl: %r", args.ttl)

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
        this_application = BIPForeignApplication(this_device, local_address)

        # start the registration process
        this_application.foreign.register(bbmd_address, args.ttl)

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
