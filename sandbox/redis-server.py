"""
Simple example that has a device object and an additional analog value object
that matches a key in Redis.
"""

import asyncio
import os

from bacpypes3.debugging import ModuleLogger
from bacpypes3.argparse import SimpleArgumentParser

from bacpypes3.primitivedata import Real
from bacpypes3.ipv4.app import Application
from bacpypes3.local.analog import AnalogValueObject

from redis import asyncio as aioredis
from redis.asyncio import Redis

# some debugging
_debug = 0
_log = ModuleLogger(globals())

# globals
redis: Redis

# settings
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))


class RedisAnalogValueObject(AnalogValueObject):
    @property
    async def presentValue(self) -> Real:
        if _debug:
            _log.debug("presentValue (getter)")

        value = await redis.get(str(self.objectName))
        if _debug:
            _log.debug(f"{value = !r}")
        if value is None:
            return None

        return Real(float(value))

    @presentValue.setter
    async def presentValue(self, value: Real) -> None:
        """Change the present value."""
        if _debug:
            _log.debug("presentValue (setter) %r", value)

        await redis.set(str(self.objectName), value)


async def main() -> None:
    global redis

    try:
        app = None
        args = SimpleArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # connect to Redis
        redis = aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
        await redis.ping()

        # build an application
        app = Application.from_args(args)
        if _debug:
            _log.debug("app: %r", app)

        # create a custom object
        custom_object = RedisAnalogValueObject(
            objectIdentifier=("analog-value", 1),
            objectName="Wowzers",
        )
        if _debug:
            _log.debug("custom_object: %r", custom_object)

        app.add_object(custom_object)

        # like running forever
        await asyncio.Future()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    asyncio.run(main())
