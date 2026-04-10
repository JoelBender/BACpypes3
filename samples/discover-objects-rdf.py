#!/usr/bin/env python

"""
Discover Devices and Object
"""

import sys
import asyncio
import argparse
import logging
from typing import List

# --- RDF Imports ---
from rdflib import Graph, Namespace  # type: ignore
from bacpypes3.rdf import BACnetGraph

# --- BACpypes3 Imports ---
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.app import Application
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.apdu import AbortPDU, ErrorRejectAbortNack
from bacpypes3.vendor import get_vendor_info

# Setup basic logging
log = logging.getLogger(__name__)

# globals
args: argparse.Namespace


def device_node(
    device_identifier: ObjectIdentifier,
) -> URIRef:
    """Given a device identifer return a URI reference for the device, the
    default function returns a value from Annex Q.8."""
    return Namespace(args.namespace)[str(device_identifier[1])]


# hack in the functions
import bacpypes3.rdf.core

bacpypes3.rdf.core._device_node = device_node


async def get_device_object_list_robust(
    app: Application, device_address: Address, device_identifier: ObjectIdentifier
) -> List[ObjectIdentifier]:
    """
    Robustly reads object list.
    """
    # 1. Try reading entire array
    try:
        obj_list = await app.read_property(
            device_address, device_identifier, "object-list"
        )
        return obj_list
    except (AbortPDU, ErrorRejectAbortNack):
        pass
    except Exception:
        sys.stderr.write(
            "error reading object-list from {device_identifier} at {device_address}: {e}\n"
        )

    obj_list = []
    try:
        # Read the Length (Index 0)
        list_len = await app.read_property(
            device_address, device_identifier, "object-list", array_index=0
        )

        # Loop through indices
        for i in range(list_len):
            object_identifier = await app.read_property(
                device_address, device_identifier, "object-list", array_index=i + 1
            )
            obj_list.append(object_identifier)
    except Exception:
        sys.stderr.write(
            "error reading object-list element from {device_identifier} at {device_address}: {e}\n"
        )
        return []

    return obj_list


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

            # get at least the basic information from the device in case it
            # doesn't support the object-list property
            for property_name in ("object-name", "description", "vendor-identifier"):
                try:
                    property_value = await app.read_property(
                        device_address, device_identifier, property_name
                    )
                    setattr(dev_graph, property_name, property_value)
                except (ErrorRejectAbortNack, AttributeError):
                    continue
                except Exception as e:
                    sys.stderr.write(
                        "error reading {property_name} from {device_identifier} at {device_address}: {e}\n"
                    )
                    continue

            # get the object list, all at once if you can
            obj_list = await get_device_object_list_robust(
                app, device_address, device_identifier
            )
            if not obj_list:
                continue

            for object_identifier in obj_list:
                obj_proxy = dev_graph.create_object(object_identifier)

                # given the object type from its object id, see if the
                # coorresponding class is supported
                obj_class = vendor_info.get_object_class(object_identifier[0])
                if not obj_class:
                    continue

                props = [
                    "object-name",
                    "object-type",
                    "description",
                    "present-value",
                    "units",
                    "reliability",
                    "out-of-service",
                    # "priority-array",
                ]

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
                    except Exception:
                        sys.stderr.write(
                            "error reading {property_name} from {object_identifier} of {device_identifier}: {e}\n"
                        )
                        continue

        print(g.serialize(format="turtle"))

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
