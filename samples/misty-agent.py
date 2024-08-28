#!/usr/bin/python3.6

import sys
import asyncio
import logging

# logging
_log = logging.getLogger(__name__)


class EchoServerProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info("peername")
        _log.debug(f"connection from {peername} via {transport}")
        self.transport = transport

    def data_received(self, data):
        _log.debug(f"received: {data!r} via {self.transport}")

        # echo it back
        self.transport.write(data)

        # _log.debug("close")
        # self.transport.close()


#
#   __main__
#


async def main():
    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    loop = asyncio.get_running_loop()

    server = await loop.create_unix_server(EchoServerProtocol, sys.argv[1])

    # async with server:
    #     await server.serve_forever()

    asyncio.ensure_future(server.serve_forever())

    await asyncio.Future()


if __name__ == "__main__":
    try:
        # turn on asyncio debugging
        if "--debug" in sys.argv:
            logging.basicConfig(level=logging.DEBUG)
            asyncio.run(main(), debug=True)
        else:
            logging.basicConfig()
            asyncio.run(main())
    except KeyboardInterrupt:
        pass
