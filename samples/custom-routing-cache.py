"""
Simple example.
"""

import asyncio
from typing import Callable, List, Optional

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.pdu import Address
from bacpypes3.app import Application
from bacpypes3.netservice import ROUTER_AVAILABLE, RouterInfo, RouterInfoCache


# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class CustomRouterInfoCache(RouterInfoCache):
    _debug: Callable[..., None]

    def get_router_info(self, snet: Optional[int], dnet: int) -> Optional[RouterInfo]:
        if _debug:
            CustomRouterInfoCache._debug("get_router_info ...")
        return None

    def update_router_info(
        self,
        snet: Optional[int],
        address: Address,
        dnets: List[int],
        status: int = ROUTER_AVAILABLE,
    ) -> None:
        if _debug:
            CustomRouterInfoCache._debug("update_router_info ...")
        return

    def update_router_status(self, snet: int, address: Address, status: int) -> None:
        if _debug:
            CustomRouterInfoCache._debug("update_router_status ...")
        return

    def delete_router_info(
        self,
        snet: int,
        address: Optional[Address] = None,
        dnets: Optional[List[int]] = None,
    ) -> None:
        if _debug:
            CustomRouterInfoCache._debug("delete_router_info ...")
        return

    def update_source_network(self, old_snet: int, new_snet: int) -> None:
        if _debug:
            CustomRouterInfoCache._debug("update_source_network ...")
        return


async def main() -> None:
    app = None
    try:
        args = SimpleArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # build an application
        app = Application.from_args(
            args,
            router_info_cache=CustomRouterInfoCache(),
        )
        if _debug:
            _log.debug("app: %r", app)

        # like running forever
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
