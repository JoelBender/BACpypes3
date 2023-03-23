"""
Simple example.
"""

import asyncio
from typing import Callable, List, Optional

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.pdu import Address
from bacpypes3.apdu import IAmRequest
from bacpypes3.app import Application, DeviceInfo, DeviceInfoCache
from bacpypes3.netservice import ROUTER_AVAILABLE, RouterInfo, RouterInfoCache


# some debugging
_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class CustomDeviceInfoCache(DeviceInfoCache):
    _debug: Callable[..., None]

    def iam_device_info(self, apdu: IAmRequest):
        """
        Create a device information record based on the contents of an
        IAmRequest and put it in the cache.
        """
        if _debug:
            CustomDeviceInfoCache._debug("iam_device_info %r", apdu)
        return super().iam_device_info(apdu)

    def get_device_info(self, key):
        if _debug:
            CustomDeviceInfoCache._debug("get_device_info %r", key)
        return super().get_device_info(key)

    def update_device_info(self, device_info):
        """
        The application has updated one or more fields in the device
        information record and the cache needs to be updated to reflect the
        changes.  If this is a cached version of a persistent record then this
        is the opportunity to update the database.
        """
        if _debug:
            CustomDeviceInfoCache._debug("update_device_info %r", device_info)
        return super().update_device_info(device_info)

    def acquire(self, device_info: DeviceInfo) -> None:
        """
        This function is called by the segmentation state machine when it
        will be using the device information.
        """
        if _debug:
            CustomDeviceInfoCache._debug("acquire %r", device_info)
        return super().acquire(device_info)

    def release(self, device_info: DeviceInfo) -> None:
        """
        This function is called by the segmentation state machine when it
        has finished with the device information.
        """
        if _debug:
            CustomDeviceInfoCache._debug("release %r", device_info)
        return super().release(device_info)


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
            device_info_cache=CustomDeviceInfoCache(),
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
