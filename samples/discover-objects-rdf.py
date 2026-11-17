#!/usr/bin/env python

"""
Discover Devices and Objects
"""

from __future__ import annotations

import sys
import asyncio
import argparse

# --- RDF Imports ---
from rdflib import Graph, Namespace, URIRef  # type: ignore
from bacpypes3.rdf import BACnetGraph
from bacpypes3.rdf.core import set_identifier_functions

# --- BACpypes3 Imports ---
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.apdu import ErrorRejectAbortNack
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

        print(g.serialize(format="turtle"))

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
