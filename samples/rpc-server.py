"""
FastAPI based simple RPC server

In addition to the BACpypes3 package, also install these packages:

    fastapi
    uvicorn[standard]

This application takes all of the usual BACpypes command line arguments and
adds a `--host` and `--port` for the web service, and `--log-level` for
uvicorn debugging.
"""
from __future__ import annotations

import asyncio
import argparse
import uvicorn
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.pdu import Address, GlobalBroadcast
from bacpypes3.primitivedata import Atomic, ObjectIdentifier
from bacpypes3.constructeddata import Sequence, AnyAtomic, Array, List
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.app import Application

# for serializing the configuration
from bacpypes3.settings import settings
from bacpypes3.json.util import (
    atomic_encode,
    sequence_to_json,
    extendedlist_to_json_list,
)

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
args: argparse.Namespace
service: Application


@asynccontextmanager
async def lifespan(app: FastAPI):
    global args, service

    # build an application
    service = Application.from_args(args)
    if _debug:
        _log.debug("lifespan service: %r", service)

    yield


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def hello_world():
    """
    Redirect to the documentation.
    """
    return RedirectResponse("/docs")


@app.get("/config")
async def config():
    """
    Return the configuration as JSON.
    """
    _log.debug("config")
    global service

    object_list = []
    for obj in service.objectIdentifier.values():
        _log.debug("    - obj: %r", obj)
        object_list.append(sequence_to_json(obj))

    return {"BACpypes": dict(settings), "application": object_list}


@app.get("/{device_instance}")
async def who_is(device_instance: int, address: Optional[str] = None):
    """
    Send out a Who-Is request and return the I-Am messages.
    """
    _log.debug("who_is %r address=%r", device_instance, address)
    global service

    # if the address is None in the who_is() call it defaults to a global
    # broadcast but it's nicer to be explicit here
    destination: Address
    if address:
        destination = Address(address)
    else:
        destination = GlobalBroadcast()
    if _debug:
        _log.debug("    - destination: %r", destination)

    # returns a list, there should be only one
    i_ams = await service.who_is(device_instance, device_instance, destination)

    result = []
    for i_am in i_ams:
        if _debug:
            _log.debug("    - i_am: %r", i_am)
        result.append(sequence_to_json(i_am))

    return result


async def _read_property(
    device_instance: int, object_identifier: str, property_identifier: str
):
    """
    Read a property from an object.
    """
    _log.debug("_read_property %r %r", device_instance, object_identifier)
    global service

    device_address: Address
    device_info = service.device_info_cache.instance_cache.get(device_instance, None)
    if device_info:
        device_address = device_info.device_address
        _log.debug("    - cached address: %r", device_address)
    else:
        # returns a list, there should be only one
        i_ams = await service.who_is(device_instance, device_instance)
        if not i_ams:
            raise HTTPException(
                status_code=400, detail=f"device not found: {device_instance}"
            )
        if len(i_ams) > 1:
            raise HTTPException(
                status_code=400, detail=f"multiple devices: {device_instance}"
            )

        device_address = i_ams[0].pduSource
        _log.debug("    - i-am response: %r", device_address)

    try:
        property_value = await service.read_property(
            device_address, ObjectIdentifier(object_identifier), property_identifier
        )
        if _debug:
            _log.debug("    - property_value: %r", property_value)
    except ErrorRejectAbortNack as err:
        if _debug:
            _log.debug("    - exception: %r", err)
        raise HTTPException(status_code=400, detail=f"error/reject/abort: {err}")

    if isinstance(property_value, AnyAtomic):
        if _debug:
            _log.debug("    - schedule objects")
        property_value = property_value.get_value()

    if isinstance(property_value, Atomic):
        encoded_value = atomic_encode(property_value)
    elif isinstance(property_value, Sequence):
        encoded_value = sequence_to_json(property_value)
    elif isinstance(property_value, (Array, List)):
        encoded_value = extendedlist_to_json_list(property_value)
    else:
        raise HTTPException(status_code=400, detail=f"JSON encoding: {property_value}")
    if _debug:
        _log.debug("    - encoded_value: %r", encoded_value)

    return {property_identifier: encoded_value}


@app.get("/{device_instance}/{object_identifier}")
async def read_present_value(device_instance: int, object_identifier: str):
    """
    Read the `present-value` property from an object.
    """
    _log.debug("read_present_value %r %r", device_instance, object_identifier)

    return await _read_property(device_instance, object_identifier, "present-value")


@app.get("/{device_instance}/{object_identifier}/{property_identifier}")
async def read_property(
    device_instance: int, object_identifier: str, property_identifier: str
):
    """
    Read a property from an object.
    """
    _log.debug("read_present_value %r %r", device_instance, object_identifier)

    return await _read_property(device_instance, object_identifier, property_identifier)


async def main() -> None:
    global app, args

    parser = SimpleArgumentParser()
    parser.add_argument(
        "--host",
        help="host address for service",
        default="0.0.0.0",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="host address for service",
        default=8000,
    )
    parser.add_argument(
        "--log-level",
        help="logging level",
        default="info",
    )
    args = parser.parse_args()
    if _debug:
        _log.debug("args: %r", args)

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
