#!/usr/bin/env python3
"""
BACnet/SC Node Device Example
=============================

Runs a minimal BACnet device that participates in a BACnet/SC network by
connecting to a hub function over a TLS-secured ("wss") WebSocket, using the
SCNodeLinkLayer wired up through a secure-connect Network Port object.

BACnet/SC requires mutual TLS authentication, so operational credentials must
be provided as PEM files:

  --cert   this node's operational certificate
  --key    the matching private key
  --ca     the accepted issuer (CA) certificate(s)

Example:
--------
    python sc-node-device.py \\
        --name SCNode --instance 3456 \\
        --hub wss://hub.example.org:47808/ \\
        --cert node.pem --key node.key --ca ca.pem

Note:
-----
For initial bring-up the credentials are supplied as file paths (the TLS
context is attached to the Network Port object).  Modelling the credentials as
BACnet File objects (Operational_Certificate_File, Issuer_Certificate_Files,
Certificate_Signing_Request_File) is a later, compliance-oriented step.
"""

import asyncio
import logging
import uuid
from argparse import ArgumentParser

from bacpypes3.app import Application
from bacpypes3.local.device import DeviceObject
from bacpypes3.local.networkport import NetworkPortObject
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.pdu import SecureConnectAddress
from bacpypes3.sc.tls import create_ssl_context
from bacpypes3.debugging import ModuleLogger

# some debugging
_debug = 0
_log = ModuleLogger(globals())


def _wss_uri(uri: str) -> str:
    """BACnet/SC only permits the 'wss' scheme; add it if a bare host:port was
    given."""
    if uri and "://" not in uri:
        return "wss://" + uri
    return uri


async def main() -> None:
    parser = ArgumentParser(description="BACnet/SC node device")
    parser.add_argument("--name", default="SCNode", help="device name")
    parser.add_argument("--instance", type=int, default=3456, help="device instance")
    parser.add_argument("--vendor", type=int, default=999, help="vendor identifier")
    parser.add_argument(
        "--hub", required=True, help="primary hub URI, e.g. wss://hub.example.org/"
    )
    parser.add_argument("--failover", default=None, help="failover hub URI")
    parser.add_argument("--cert", required=True, help="operational certificate (PEM)")
    parser.add_argument("--key", required=True, help="private key (PEM)")
    parser.add_argument("--ca", required=True, help="issuer/CA certificate(s) (PEM)")
    parser.add_argument(
        "--debug", action="store_true", help="show BACnet/SC connection logging"
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s"
        )
        logging.getLogger("bacpypes3.sc.service").setLevel(logging.DEBUG)
    else:
        # at least surface connection warnings (TLS/connect failures)
        logging.basicConfig(level=logging.WARNING)

    # every BACnet/SC device requires a stable device UUID (Clause YY.1.5.3)
    device_object = DeviceObject(
        objectIdentifier=("device", args.instance),
        objectName=args.name,
        vendorIdentifier=args.vendor,
        deviceUUID=uuid.uuid4().bytes,
    )

    # a secure-connect network port with a Random-48 VMAC
    primary_hub_uri = _wss_uri(args.hub)
    failover_hub_uri = _wss_uri(args.failover) if args.failover else ""
    network_port = NetworkPortObject(
        SecureConnectAddress.random(),
        objectIdentifier=("network-port", 1),
        objectName="SC Port 1",
        scPrimaryHubURI=primary_hub_uri,
        scFailoverHubURI=failover_hub_uri,
    )

    # attach the mutual-TLS context (v1 file-path credentials) so the link
    # layer can establish the secured WebSocket connection to the hub.  A
    # leading underscore stores it as plain data, bypassing the BACnet
    # property machinery on the local object.
    network_port._ssl_context = create_ssl_context(args.cert, args.key, args.ca)

    # a sample point to read
    analog_value = AnalogValueObject(
        objectIdentifier=("analogValue", 1),
        objectName="temperature",
        presentValue=21.5,
    )

    app = Application.from_object_list([device_object, network_port, analog_value])
    _log.info("running as %s on %s", args.name, primary_hub_uri)

    # report hub connection status
    link_layer = app.link_layers.get(network_port.objectIdentifier)

    async def monitor() -> None:
        connector = link_layer.connector
        was_connected = False
        while True:
            is_connected = connector.connected.is_set()
            if is_connected and not was_connected:
                print(f"connected to hub {connector.peer_vmac} ({connector.peer_uuid})")
            elif was_connected and not is_connected:
                print("hub connection lost")
            was_connected = is_connected
            await asyncio.sleep(1.0)

    monitor_task = asyncio.ensure_future(monitor())

    try:
        await asyncio.Future()
    finally:
        monitor_task.cancel()
        app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
