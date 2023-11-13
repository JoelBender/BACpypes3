"""
Simple example that sends a Who-Is request and for each device that responds,
reads the object list and reads the object name, description, and present-value
and units if applicable.
"""

import sys
import asyncio

from typing import List, Optional

from bacpypes3.debugging import bacpypes_debugging, ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.apdu import AbortReason, AbortPDU, ErrorRejectAbortNack
from bacpypes3.app import Application
from bacpypes3.vendor import get_vendor_info

from rdflib import Graph  # type: ignore
from bacpypes3.rdf import BACnetGraph


# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
show_warnings: bool = False


@bacpypes_debugging
async def object_identifiers(
    app: Application, device_address: Address, device_identifier: ObjectIdentifier
) -> List[ObjectIdentifier]:
    """
    Read the entire object list from a device at once, or if that fails, read
    the object identifiers one at a time.
    """
    if _debug:
        object_identifiers._debug("object_identifiers ...")

    # try reading the whole thing at once, but it might be too big and
    # segmentation isn't supported
    try:
        object_list = await app.read_property(
            device_address, device_identifier, "object-list"
        )
        if _debug:
            object_identifiers._debug("    - object_list: %r", object_list)

        return object_list
    except AbortPDU as err:
        if err.apduAbortRejectReason in (
            AbortReason.bufferOverflow,
            AbortReason.segmentationNotSupported,
        ):
            if _debug:
                object_identifiers._debug("    - object_list err: %r", err)
        else:
            if show_warnings:
                sys.stderr.write(f"{device_identifier} object-list abort: {err}\n")
            return []
    except ErrorRejectAbortNack as err:
        if show_warnings:
            sys.stderr.write(f"{device_identifier} object-list error/reject: {err}\n")
        return []

    # fall back to reading the length and each element one at a time
    object_list = []
    try:
        # read the length
        object_list_length = await app.read_property(
            device_address,
            device_identifier,
            "object-list",
            array_index=0,
        )
        if _debug:
            object_identifiers._debug(
                "    - object_list_length: %r", object_list_length
            )

        # read each element individually
        for i in range(object_list_length):
            object_identifier = await app.read_property(
                device_address,
                device_identifier,
                "object-list",
                array_index=i + 1,
            )
            object_list.append(object_identifier)
    except ErrorRejectAbortNack as err:
        if show_warnings:
            sys.stderr.write(
                f"{device_identifier} object-list length error/reject: {err}\n"
            )

    return object_list


async def main() -> None:
    app = None
    g = Graph()
    bacnet_graph = BACnetGraph(g)

    try:
        parser = SimpleArgumentParser()
        parser.add_argument(
            "device_identifier",
            type=int,
            help="device identifier",
        )
        parser.add_argument(
            "-o",
            "--output",
            help="output to a file",
        )
        parser.add_argument(
            "-f",
            "--format",
            help="output format",
            default="turtle",
        )

        # add an option to show warnings (argparse.BooleanOptionalAction is 3.9+)
        warnings_parser = parser.add_mutually_exclusive_group(required=False)
        warnings_parser.add_argument("--warnings", dest="warnings", action="store_true")
        warnings_parser.add_argument(
            "--no-warnings", dest="warnings", action="store_false"
        )
        parser.set_defaults(warnings=False)

        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # percolate up to the global
        show_warnings = args.warnings

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # look for the device
        i_ams = await app.who_is(args.device_identifier, args.device_identifier)
        if not i_ams:
            sys.stderr.write("device not found\n")
            sys.exit(1)

        i_am = i_ams[0]
        if _debug:
            _log.debug("    - i_am: %r", i_am)

        device_address: Address = i_am.pduSource
        device_identifier: ObjectIdentifier = i_am.iAmDeviceIdentifier
        vendor_info = get_vendor_info(i_am.vendorID)
        if _debug:
            _log.debug("    - vendor_info: %r", vendor_info)

        # create a device object in the graph and return it like a context
        device_graph = bacnet_graph.create_device(device_address, device_identifier)
        if _debug:
            _log.debug("    - device_graph: %r", device_graph)

        object_list = await object_identifiers(app, device_address, device_identifier)
        for object_identifier in object_list:
            if _debug:
                _log.debug("    - object_identifier: %r", object_identifier)

            # create an object relative to the device and return it like a context
            object_proxy = device_graph.create_object(object_identifier)
            if _debug:
                _log.debug("    - object_proxy: %r", object_proxy)

            # get the class so we know the datatypes of the properties
            object_class = vendor_info.get_object_class(object_identifier[0])
            if _debug:
                _log.debug("    - object_class: %r", object_class)
            if object_class is None:
                if show_warnings:
                    sys.stderr.write(f"unknown object type: {object_identifier}\n")
                continue

            # read the property list
            property_list: Optional[List[PropertyIdentifier]] = None
            try:
                property_list = await app.read_property(
                    device_address, object_identifier, "property-list"
                )
                if _debug:
                    _log.debug("    - property_list: %r", property_list)
                assert isinstance(property_list, list)

                setattr(
                    object_proxy,
                    "property-list",
                    property_list,
                )
            except ErrorRejectAbortNack as err:
                if show_warnings:
                    sys.stderr.write(
                        f"{object_identifier} property-list error: {err}\n"
                    )

            for property_name in (
                "object-name",
                "description",
                "present-value",
                "units",
            ):
                try:
                    if _debug:
                        _log.debug("    - property_name: %r", property_name)

                    # don't bother attempting to read the property if the object
                    # doesn't say it exists
                    property_identifier = PropertyIdentifier(property_name)
                    if property_list and property_identifier not in property_list:
                        continue

                    # get the property class, if it doesn't exist then the
                    # property isn't defined for this object type
                    property_class = object_class.get_property_type(property_identifier)
                    if property_class is None:
                        if show_warnings:
                            sys.stderr.write(
                                f"{object_identifier} unknown property: {property_identifier}\n"
                            )
                        continue
                    if _debug:
                        _log.debug("    - property_class: %r", property_class)

                    property_value = await app.read_property(
                        device_address, object_identifier, property_identifier
                    )
                    setattr(object_proxy, property_name, property_value)

                except ErrorRejectAbortNack as err:
                    if show_warnings:
                        sys.stderr.write(
                            f"{object_identifier} {property_name} error: {err}\n"
                        )

        # dump the graph
        if args.output:
            with open(args.output, "wb") as ttl_file:
                g.serialize(ttl_file, format=args.format)
        else:
            g.serialize(sys.stdout.buffer, format=args.format)

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
