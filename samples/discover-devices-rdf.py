"""
Simple example that sends a Who-Is request and writes an RDF graph (Turtle)
to stdout with a bacnet:Device node for each device that responds.  Each node
has the bacnet:device-instance and bacnet:device-address of the device, as
described by the bacnet:Device shape in the csml2rdf bacnet.ttl ontology.
"""

from __future__ import annotations

import sys
import asyncio
import argparse

from rdflib import Graph, Namespace, URIRef  # type: ignore

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.app import Application
from bacpypes3.rdf import BACnetGraph
from bacpypes3.rdf.core import set_identifier_functions

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
args: argparse.Namespace


def device_node(
    device_identifier: ObjectIdentifier,
) -> URIRef:
    """Given a device identifier return a URI reference for the device in the
    namespace from the command line, for example ns:510."""
    return Namespace(args.namespace)[str(device_identifier[1])]


# use this function for device node identifiers
set_identifier_functions(device_node_fn=device_node)


async def main() -> None:
    global args

    app = None
    try:
        parser = SimpleArgumentParser()
        parser.add_argument(
            "low_limit",
            type=int,
            help="device instance range low limit",
        )
        parser.add_argument(
            "high_limit",
            type=int,
            help="device instance range high limit",
        )
        parser.add_argument(
            "--namespace",
            default="http://example.com/",
            help="namespace for the device nodes",
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # build a graph for the devices
        g = Graph()
        bacnet_graph = BACnetGraph(g)
        bacnet_graph.bind_namespace("ns", args.namespace)

        # the first address each device responded from
        device_addresses: dict[int, Address] = {}

        # run the query
        i_ams = await app.who_is(args.low_limit, args.high_limit)
        for i_am in i_ams:
            if _debug:
                _log.debug("    - i_am: %r", i_am)

            device_address: Address = i_am.pduSource
            device_identifier: ObjectIdentifier = i_am.iAmDeviceIdentifier
            device_instance = device_identifier[1]

            # a device can respond more than once (for example through two
            # routers), the shape allows only one device-address
            if device_instance in device_addresses:
                if device_address != device_addresses[device_instance]:
                    sys.stderr.write(
                        f"{device_identifier} also at {device_address}, "
                        f"keeping {device_addresses[device_instance]}\n"
                    )
                continue
            device_addresses[device_instance] = device_address

            # a bacnet:Device node with its device-instance and device-address
            bacnet_graph.create_device(device_address, device_identifier)

        print(g.serialize(format="turtle"))

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
