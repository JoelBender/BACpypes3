"""
Simple console example that sends Read Property service requests and can
interpret custom object types and properties.
"""

import sys
import asyncio

from typing import Callable, Optional

from bacpypes3.settings import settings
from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd

from bacpypes3.pdu import Address
from bacpypes3.comm import bind
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.constructeddata import AnyAtomic
from bacpypes3.object import get_vendor_info
from bacpypes3.app import Application, DeviceInfo
from bacpypes3.apdu import ErrorRejectAbortNack

# talking to a custom server, importing this module registers the
# custom object types and properties
import custom  # noqa: F401

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
app: Application = None


@bacpypes_debugging
class SampleCmd(Cmd):
    """
    Sample Cmd
    """

    _debug: Callable[..., None]

    async def do_read(
        self,
        address: Address,
        objid: str,
        prop: str,
        array_index: Optional[int] = None,
    ) -> None:
        """
        usage: read address objid prop [ indx ]
        """
        if _debug:
            SampleCmd._debug("do_read %r %r %r %r", address, objid, prop, array_index)
        assert app

        # get information about the device from the application
        device_info = app.device_info_cache.get_device_info(address)
        if _debug:
            SampleCmd._debug("    - device_info: %r", device_info)

        # using the device info, look up the vendor information
        if device_info:
            vendor_info = get_vendor_info(device_info.vendorID)
        else:
            vendor_info = get_vendor_info(0)
        if _debug:
            SampleCmd._debug("    - vendor_info: %r", vendor_info)

        # translate the strings to identifiers according to the vendor
        object_identifier = vendor_info.object_identifier(objid)
        if _debug:
            SampleCmd._debug("    - object_identifier: %r", object_identifier)
        property_identifier = vendor_info.property_identifier(prop)
        if _debug:
            SampleCmd._debug("    - property_identifier: %r", property_identifier)

        try:
            response = await app.read_property(
                address, object_identifier, property_identifier, array_index
            )
            if _debug:
                SampleCmd._debug("    - response: %r", response)
        except ErrorRejectAbortNack as err:
            if _debug:
                SampleCmd._debug("    - exception: %r", err)
            response = err

        if isinstance(response, AnyAtomic):
            if _debug:
                SampleCmd._debug("    - schedule objects")
            response = response.get_value()

        await self.response(str(response))

    def do_debug(self) -> None:
        print(app.device_info_cache.cache)


async def main() -> None:
    global app

    try:
        console = cmd = app = None
        parser = SimpleArgumentParser()
        parser.add_argument(
            "peer_id",
            type=str,
            help="custom peer device identifier",
        )
        parser.add_argument(
            "peer_address",
            type=str,
            help="custom peer network address",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("settings: %r", settings)

        # evaluate the peer device identifier
        peer_id = ObjectIdentifier(args.peer_id)
        if peer_id[0] != 8:
            raise ValueError(f"device identifier expected: {peer_id}")

        # evaluate the peer address
        peer_address = Address(args.peer_address)
        if _debug:
            _log.debug("peer_address: %r", peer_address)

        # build a very small stack
        console = Console()
        cmd = SampleCmd()
        bind(console, cmd)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # give the application some device information, usually from an I-Am
        other_device_info = DeviceInfo(args.peer_id, peer_address)
        other_device_info.vendorID = 888
        app.device_info_cache.update_device_info(other_device_info)

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
