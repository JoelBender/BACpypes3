"""
Simple application that has a device object
"""

import asyncio

from typing import Optional

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import INIArgumentParser

from bacpypes3.pdu import Address, IPv4Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import ServicesSupported
from bacpypes3.apdu import AbortReason, AbortPDU, ErrorRejectAbortNack
from bacpypes3.ipv4.app import Application, NormalApplication
from bacpypes3.local.device import DeviceObject

# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
async def discover(app: Application, lowlimit: int, highlimit: int) -> None:
    i_ams = await app.who_is(lowlimit, highlimit)
    for i_am in i_ams:
        if _debug:
            discover._debug("    - i_am: %r", i_am)

        device_address: Address = i_am.pduSource
        device_identifier: ObjectIdentifier = i_am.iAmDeviceIdentifier

        try:
            device_supports_read_property_multiple = False
            protocol_services_supported = await app.read_property(
                device_address, device_identifier, "protocolServicesSupported"
            )
            print(
                device_identifier,
                " protocolServicesSupported: ",
                protocol_services_supported,
            )
            device_supports_read_property_multiple = (
                ServicesSupported.readPropertyMultiple in protocol_services_supported
            )
        except ErrorRejectAbortNack as err:
            print(
                device_identifier,
                " protocolServicesSupported error: ",
                err,
            )

        object_list = await object_identifiers(app, device_address, device_identifier)
        for object_identifier in object_list:
            try:
                object_name = await app.read_property(
                    device_address, object_identifier, "objectName"
                )
                print("    ", object_identifier, " objectName: ", object_name)
            except ErrorRejectAbortNack as err:
                print(
                    device_identifier,
                    " objectName error: ",
                    object_name,
                    type(object_name),
                )
                continue


@bacpypes_debugging
async def object_identifiers(
    app: Application, device_address: Address, device_identifier: ObjectIdentifier
) -> None:
    """
    Read the entire object list at once, or if that fails, read the object
    identifiers one at a time.
    """

    # try reading the whole thing at once
    try:
        object_list = await app.read_property(
            device_address, device_identifier, "objectList"
        )
        return object_list
    except AbortPDU as err:
        if err.apduAbortRejectReason != AbortReason.segmentationNotSupported:
            print(
                device_identifier,
                " objectList abort: ",
                err,
                type(err),
            )
            return []
    except ErrorRejectAbortNack as err:
        print(
            device_identifier,
            " objectList error/reject: ",
            err,
            type(err),
        )
        return []

    object_list = []
    try:
        # read the length
        object_list_length = await app.read_property(
            device_address,
            device_identifier,
            "objectList",
            array_index=0,
        )

        # read each element individually
        for i in range(object_list_length):
            object_identifier = await app.read_property(
                device_address,
                device_identifier,
                "objectList",
                array_index=i + 1,
            )
            object_list.append(object_identifier)
    except ErrorRejectAbortNack as err:
        print(
            device_identifier,
            " objectList error: ",
            err,
            type(err),
        )

    return object_list


def main() -> None:
    app: Optional[NormalApplication] = None

    try:
        # get the event loop
        loop = asyncio.get_event_loop()

        parser = INIArgumentParser()
        parser.add_argument(
            "lowlimit",
            type=int,
            help="device instance low limit",
        )
        parser.add_argument(
            "highlimit",
            type=int,
            help="device instance high limit",
        )

        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # evaluate the address in the INI file
        ipv4_address = IPv4Address(args.ini.address)
        if _debug:
            _log.debug("ipv4_address: %r", ipv4_address)

        # make a device object
        this_device = DeviceObject(
            objectIdentifier=("device", 1),
            objectName="test",
            vendorIdentifier=999,
        )
        if _debug:
            _log.debug("this_device: %r", this_device)

        # build the application
        app = NormalApplication(this_device, ipv4_address)
        if _debug:
            _log.debug("app: %r", app)

        # just keep running
        loop.run_until_complete(discover(app, args.lowlimit, args.highlimit))

    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
    finally:
        if app:
            app.server.close()
        if loop:
            loop.close()


if __name__ == "__main__":
    main()
