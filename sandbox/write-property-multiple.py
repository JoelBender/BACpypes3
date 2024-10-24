import sys
import asyncio
from typing import Callable

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.console import Console

from bacpypes3.cmd import Cmd
from bacpypes3.pdu import Address
from bacpypes3.comm import bind
from bacpypes3.basetypes import PropertyReference, WriteAccessSpecification
from bacpypes3.primitivedata import ObjectIdentifier, Real, Unsigned
from bacpypes3.apdu import (
    ErrorRejectAbortNack,
    WritePropertyMultipleRequest,
    PropertyValue,
)
from bacpypes3.app import Application

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
app: Application = None


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Cmd for WritePropertyMultiple
    """

    _debug: Callable[..., None]

    async def do_wpm(
        self,
        address: Address,
        *args: str,
    ) -> None:
        """
        usage: wpm address ( objid prop value priority )...
        """
        if _debug:
            SampleCmd._debug("do_wpm %r %r", address, args)

        # ensure proper argument structure
        if len(args) % 4 != 0:
            await self.response(
                "Each property write requires: objid prop value priority"
            )
            return

        args = list(args)
        parameter_list = []

        while args:
            # extract the object identifier, property identifier, value, and priority
            object_identifier = ObjectIdentifier(args.pop(0))
            property_identifier = args.pop(0)
            value = Real(float(args.pop(0)))  # assuming you're writing to Real values
            priority = Unsigned(int(args.pop(0)))

            # create PropertyReference to parse the arg
            property_reference = PropertyReference(property_identifier)

            # construct PropertyValue (with priority)
            property_value = PropertyValue(
                propertyIdentifier=property_reference.propertyIdentifier,
                value=value,
                priority=priority,
            )

            # build the write access specification
            write_access_spec = WriteAccessSpecification(
                objectIdentifier=object_identifier,
                listOfProperties=[property_value],  # list of PropertyValue
            )

            parameter_list.append(write_access_spec)

        if not parameter_list:
            await self.response("No properties to write")
            return

        try:
            # create WritePropertyMultipleRequest
            write_property_multiple_request = WritePropertyMultipleRequest(
                listOfWriteAccessSpecs=parameter_list,
                destination=address,
            )

            # send the request
            response = await app.request(write_property_multiple_request)
            if _debug:
                SampleCmd._debug("    - response: %r", response)

            if isinstance(response, ErrorRejectAbortNack):
                await self.response(f"Error: {response}")
            else:
                await self.response("Write successful!")

        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            await self.response(f"Error: {err}")


async def main() -> None:
    global app

    try:
        console = cmd = app = None
        parser = SimpleArgumentParser()
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)
            _log.debug("settings: %r", settings)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

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
