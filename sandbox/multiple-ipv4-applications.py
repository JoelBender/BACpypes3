"""
Simple example of a BACnet/IP application that runs multiple applications on the same host.
"""

import asyncio
from argparse import Namespace
from bacpypes3.app import Application


async def main() -> None:
    common_kwargs = {
        "network": None,
        "foreign": None,
        "bbmd": None,
        "vendoridentifier": 999,
    }
    app1 = Application.from_args(
        Namespace(
            name="App1", instance=1001, address="host:47808", **common_kwargs
        )
    )
    app2 = Application.from_args(
        Namespace(
            name="App2", instance=1002, address="host:47809", **common_kwargs
        )
    )

    # like running forever
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
