"""
MQTT A-side Example

When a payload from a broker is received, look up the topic name and map it to
a Write Property Request.
"""

import asyncio

from typing import Dict, Tuple

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.app import Application
from bacpypes3.apdu import ErrorRejectAbortNack

import aiomqtt

# some debugging
_debug = 0
_log = ModuleLogger(globals())

MQTT_HOST = "test.mosquitto.org"
MQTT_TOPIC_PREFIX = "bacpypes3/mqtt"

topic_map: Dict[str, Tuple] = {
    "oat": (
        Address("host:47809"),
        ObjectIdentifier("analog-value,1"),
        PropertyIdentifier("present-value"),
        None,  # property_array_index
        None,  # priority
    ),
    "rh": (
        Address("host:47809"),
        ObjectIdentifier("analog-value,2"),
        PropertyIdentifier("present-value"),
        None,  # property_array_index
        None,  # priority
    ),
}


async def main() -> None:
    app = None
    try:
        parser = SimpleArgumentParser()
        parser.add_argument(
            "--topic",
            help="topic prefix",
            default=MQTT_TOPIC_PREFIX,
        )
        parser.add_argument(
            "--host",
            help="host name of the broker",
            default=MQTT_HOST,
        )
        args = parser.parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # connect to the broker
        async with aiomqtt.Client(args.host) as client:
            await client.subscribe(args.topic + "/#")
            async for message in client.messages:
                if _debug:
                    _log.debug("topic, payload: %r, %r", message.topic, message.payload)

                topic = str(message.topic)[len(args.topic) + 1 :]
                if topic not in topic_map:
                    continue

                # get the service parameters
                (
                    device_address,
                    object_identifier,
                    property_identifier,
                    property_array_index,
                    priority,
                ) = topic_map[topic]

                try:
                    response = await app.write_property(
                        device_address,
                        object_identifier,
                        property_identifier,
                        message.payload.decode(),
                        property_array_index,
                        priority,
                    )
                    if _debug:
                        _log.debug("response: %r", response)
                except ErrorRejectAbortNack as err:
                    print(f"{device_address}, {object_identifier}: {err}")

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
