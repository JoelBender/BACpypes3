#!/usr/bin/env python

"""
Discover Devices and Objects
"""

from __future__ import annotations

import sys
import asyncio
import argparse

from typing import Any

# --- RDF Imports ---
from rdflib import Graph, Namespace, URIRef  # type: ignore
from bacpypes3.rdf import BACnetGraph
from bacpypes3.rdf.core import set_identifier_functions

# --- BACpypes3 Imports ---
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import (
    ErrorType,
    ObjectType,
    PropertyIdentifier,
    ServicesSupported,
)
from bacpypes3.apdu import ErrorRejectAbortNack, IAmRequest
from bacpypes3.vendor import get_vendor_info

# globals
args: argparse.Namespace


def device_node(
    device_identifier: ObjectIdentifier,
) -> URIRef:
    """Given a device identifer return a URI reference for the device, the
    default function returns a value from Annex Q.8."""
    return Namespace(args.namespace)[str(device_identifier[1])]


# use this function for device node identifiers
set_identifier_functions(device_node_fn=device_node)


# properties written by DeviceGraph.create_object, no need to read them
CREATED_PROPERTIES = ("object-identifier", "object-type")

# optional properties that are interesting enough to read when supported
OPTIONAL_PROPERTIES = ("description", "reliability")


def required_properties(obj_class: type) -> list[str]:
    """
    Return the names of the required properties of an object class.  Each
    class only lists its own required properties in `_required`, so collect
    them from the class and all of its base classes, base classes first.
    """
    property_names: list[str] = []
    for cls in reversed(obj_class.__mro__):
        for attr in cls.__dict__.get("_required", ()):
            property_name = str(PropertyIdentifier(attr))
            if property_name not in property_names:
                property_names.append(property_name)
    return property_names


async def supports_rpm(app: Application, i_am: IAmRequest) -> bool:
    """
    Return True if the device supports Read Property Multiple, based on its
    protocol-services-supported property, which is cached in the device
    information (same logic as bacpypes3.lib.batchread).
    """
    device_address = i_am.pduSource

    # the I-Am processing caches the device information in a separate task,
    # so it might not be there yet
    device_info = await app.device_info_cache.get_device_info(device_address)
    if not device_info:
        device_info = await app.device_info_cache.set_device_info(i_am)

    # see if protocol-services-supported is cached
    if device_info.protocol_services_supported is None:
        try:
            device_info.protocol_services_supported = await app.read_property(
                device_address,
                ObjectIdentifier((ObjectType.device, device_info.device_instance)),
                "protocol-services-supported",
            )
        except ErrorRejectAbortNack:
            device_info.protocol_services_supported = ServicesSupported([])

    return bool(device_info.protocol_services_supported["read-property-multiple"])


async def read_properties_rpm(
    app: Application,
    device_address: Address,
    object_identifier: ObjectIdentifier,
    obj_proxy: Any,
) -> bool:
    """
    Read the required properties and the interesting optional ones of an
    object with a single Read Property Multiple request.  Return False if the
    request failed so the caller can fall back to reading the properties one
    at a time.

    The property-list property is not returned when reading 'required' (or
    'all') so it is requested explicitly.
    """
    try:
        results = await app.read_property_multiple(
            device_address,
            [
                object_identifier,
                [PropertyIdentifier.required, "property-list", *OPTIONAL_PROPERTIES],
            ],
        )
    except ErrorRejectAbortNack:
        return False
    except Exception as e:
        sys.stderr.write(
            f"error reading {object_identifier} at {device_address} with RPM: {e!r}\n"
        )
        return False

    # errors and invalid responses are returned rather than raised
    if (results is None) or isinstance(results, ErrorRejectAbortNack):
        return False

    for _, property_identifier, property_array_index, value in results:
        property_name = str(property_identifier)
        if property_name in CREATED_PROPERTIES:
            continue

        # property access errors, unknown datatypes, array elements
        if (
            (value is None)
            or isinstance(value, ErrorType)
            or (property_array_index is not None)
        ):
            continue

        try:
            setattr(obj_proxy, property_name, value)
        except AttributeError:
            continue

    return True


async def read_properties_individually(
    app: Application,
    device_address: Address,
    device_identifier: ObjectIdentifier,
    object_identifier: ObjectIdentifier,
    obj_class: type,
    obj_proxy: Any,
) -> None:
    """
    Read the required properties and the interesting optional ones of an
    object one at a time.
    """
    # all of the required properties and some optional ones
    props = [
        property_name
        for property_name in required_properties(obj_class)
        if property_name not in CREATED_PROPERTIES
    ]
    props.extend(
        property_name
        for property_name in OPTIONAL_PROPERTIES
        if property_name not in props
    )

    for property_name in props:
        property_identifier = PropertyIdentifier(property_name)

        # given a property identifier, see if the property is
        # supported by checking the class
        if not obj_class.get_property_type(property_identifier):
            continue

        try:
            val = await app.read_property(
                device_address, object_identifier, property_identifier
            )

            # Add to RDF
            setattr(obj_proxy, property_name, val)

        except (ErrorRejectAbortNack, AttributeError):
            continue
        except Exception as e:
            sys.stderr.write(
                f"error reading {property_name} from {object_identifier} of {device_identifier}: {e}\n"
            )
            continue


async def main() -> None:
    global args

    # 1. Parse Arguments
    parser = SimpleArgumentParser()
    parser.add_argument("low", type=int, help="Device Instance Low Limit")
    parser.add_argument("high", type=int, help="Device Instance High Limit")
    parser.add_argument("--namespace", default="http://example.com/", help="Namespace")
    args = parser.parse_args()

    # 2. Setup App
    app = Application.from_args(args)

    try:
        i_ams = await app.who_is(args.low, args.high)
        if not i_ams:
            return

        # Init RDF
        g = Graph()
        bacnet_graph = BACnetGraph(g)
        bacnet_graph.bind_namespace("ns", args.namespace)

        for i_am in i_ams:
            device_address = i_am.pduSource
            device_identifier = i_am.iAmDeviceIdentifier
            vendor_info = get_vendor_info(i_am.vendorID)

            # RDF Device Node
            dev_graph = bacnet_graph.create_device(device_address, device_identifier)
            dev_obj = dev_graph.create_object(device_identifier)

            # check for Read Property Multiple support
            use_rpm = await supports_rpm(app, i_am)
            sys.stderr.write(
                f"{device_identifier} at {device_address}: "
                f"{'using' if use_rpm else 'not using'} ReadPropertyMultiple\n"
            )

            # get at least the basic information from the device in case it
            # doesn't support the object-list property
            for property_name in ("object-name", "description", "vendor-identifier"):
                try:
                    property_value = await app.read_property(
                        device_address, device_identifier, property_name
                    )
                    setattr(dev_obj, property_name, property_value)
                except (ErrorRejectAbortNack, AttributeError):
                    continue
                except Exception as e:
                    sys.stderr.write(
                        f"error reading {property_name} from {device_identifier} at {device_address}: {e}\n"
                    )
                    continue

            # get the object list, all at once if possible, otherwise one
            # element at a time
            try:
                obj_list = await app.read_object_list(
                    device_address, device_identifier
                )
            except (ErrorRejectAbortNack, Exception) as e:
                sys.stderr.write(
                    f"error reading object-list from {device_identifier} at {device_address}: {e}\n"
                )
                obj_list = []

            # the device object is always there, even when the object list
            # is empty or could not be read, so read its required properties
            obj_list = list(obj_list)
            if device_identifier not in obj_list:
                obj_list.insert(0, device_identifier)

            for object_identifier in obj_list:
                obj_proxy = dev_graph.create_object(object_identifier)

                # given the object type from its object id, see if the
                # corresponding class is supported
                obj_class = vendor_info.get_object_class(object_identifier[0])
                if not obj_class:
                    continue

                # all at once if possible, otherwise one at a time
                if not (
                    use_rpm
                    and await read_properties_rpm(
                        app, device_address, object_identifier, obj_proxy
                    )
                ):
                    await read_properties_individually(
                        app,
                        device_address,
                        device_identifier,
                        object_identifier,
                        obj_class,
                        obj_proxy,
                    )

        print(g.serialize(format="turtle"))

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
