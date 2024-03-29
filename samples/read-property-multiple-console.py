"""
Simple console example that sends read property multiple requests.  This
version just builds the parameter list leaving everything as strings, it
will be converted to the appropriate types inside the method.
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
from bacpypes3.basetypes import ErrorType

from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.ipv4.app import NormalApplication
from bacpypes3.local.device import DeviceObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
app: NormalApplication = None


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_rpm(
        self,
        address: Address,
        *args: str,
    ) -> None:
        """
        usage: rpm address ( objid ( prop[indx] )... )...
        """
        if _debug:
            SampleCmd._debug("do_rpm %r %r", address, args)
        args = list(args)

        parameter_list = []
        while args:
            # grab the object identifier
            object_identifier = args.pop(0)
            parameter_list.append(object_identifier)

            property_reference_list = []
            while args:
                # next thing is a property reference
                property_reference = args.pop(0)
                property_reference_list.append(property_reference)

                # crude check to see if the next thing is an object identifier
                if args and ((":" in args[0]) or ("," in args[0])):
                    break

            parameter_list.append(property_reference_list)

        if not parameter_list:
            await self.response("object identifier expected")
            return

        try:
            response = await app.read_property_multiple(address, parameter_list)
            if _debug:
                SampleCmd._debug("    - response: %r", response)
        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            response = err

        # dump out the results
        for (
            object_identifier,
            property_identifier,
            property_array_index,
            property_value,
        ) in response:
            if property_array_index is not None:
                await self.response(
                    f"{object_identifier} {property_identifier}[{property_array_index}] {property_value}"
                )
            else:
                await self.response(
                    f"{object_identifier} {property_identifier} {property_value}"
                )
            if isinstance(property_value, ErrorType):
                await self.response(
                    f"    {property_value.errorClass}, {property_value.errorCode}"
                )


async def main() -> None:
    global app

    try:
        console = cmd = app = None
        parser = ArgumentParser()
        parser.add_argument(
            "address",
            type=str,
            help="address",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)
            _log.debug("settings: %r", settings)

        # evaluate the address
        ipv4_address = IPv4Address(args.address)
        if _debug:
            _log.debug("ipv4_address: %r", ipv4_address)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # make a device object
        local_device = DeviceObject(
            objectIdentifier=("device", 1),
            objectName="test",
            vendorIdentifier=999,
        )
        if _debug:
            _log.debug("local_device: %r", local_device)

        # build the application
        app = NormalApplication(local_device, ipv4_address)
        if _debug:
            _log.debug("app: %r", app)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if app:
            app.close()
        if console and console.exit_status:
            sys.exit(console.exit_status)


if __name__ == "__main__":
    asyncio.run(main())
