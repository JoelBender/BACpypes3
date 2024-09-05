"""
MQTT B-side Example

When the present-value of an Analog Object is changed, publish a message to the
broker using the object name as the topic.
"""

import asyncio

from typing import Dict, Tuple

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.primitivedata import ObjectIdentifier, Real
from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogValueObject

import aiomqtt

# some debugging
_debug = 0
_log = ModuleLogger(globals())

MQTT_HOST = "test.mosquitto.org"
MQTT_TOPIC_PREFIX = "bacpypes3/mqtt"

# globals
args = None
client = None

topic_map: Dict[str, ObjectIdentifier] = {
    "oat": ObjectIdentifier("analog-value,1"),
    "rh": ObjectIdentifier("analog-value,2"),
}


class MQTTAnalogValueObject(AnalogValueObject):
    _present_value: float = 0.0

    @property
    async def presentValue(self) -> Real:
        if _debug:
            _log.debug("presentValue (getter)")

        return Real(self._present_value)

    @presentValue.setter
    async def presentValue(self, value: Real) -> None:
        """Change the present value."""
        if _debug:
            _log.debug("presentValue (setter) %r", value)
        global client

        self._present_value = value

        await client.publish(args.topic + "/" + self.objectName, payload=value)


async def main() -> None:
    global args, client

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

        # create objects
        for object_name, object_identifier in topic_map.items():
            # create a custom object
            analog_value_object = MQTTAnalogValueObject(
                objectName=object_name,
                objectIdentifier=(object_identifier),
                presentValue=0.0,
            )
            if _debug:
                _log.debug("analog_value_object: %r", analog_value_object)

            app.add_object(analog_value_object)

        # connect and run forever
        async with aiomqtt.Client(args.host) as client:
            await asyncio.Future()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
