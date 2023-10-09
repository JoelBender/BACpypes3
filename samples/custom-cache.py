"""
Simple example.
"""

import asyncio

from typing import Callable, List, Optional, Tuple, Union

from bacpypes3.debugging import ModuleLogger, bacpypes_debugging
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.console import Console
from bacpypes3.cmd import Cmd
from bacpypes3.comm import bind

from bacpypes3.pdu import Address
from bacpypes3.apdu import IAmRequest
from bacpypes3.basetypes import (
    Segmentation,
)
from bacpypes3.app import Application, DeviceInfo, DeviceInfoCache
from bacpypes3.netservice import (
    ROUTER_AVAILABLE,
    RouterInfo,
    RouterInfoCache,
    NetworkAdapter,
)
from bacpypes3.npdu import IAmRouterToNetwork

from redis import asyncio as aioredis
from redis.asyncio import Redis


# some debugging
_debug = 0
_log = ModuleLogger(globals())


# settings
DEVICE_INFO_CACHE_EXPIRE = 30  # seconds

# globals
app: Application
redis: Redis


@bacpypes_debugging
class CustomDeviceInfo(DeviceInfo):
    def encode(self) -> bytes:
        if _debug:
            CustomDeviceInfo._debug("encode")

        contents = ",".join(
            [
                str(x)
                for x in (
                    self.deviceIdentifier,
                    self.address,
                    self.max_apdu_length_accepted,
                    self.segmentation_supported,
                    self.vendor_identifier,
                )
            ]
        )
        if _debug:
            CustomDeviceInfo._debug("    - contents: %r", contents)

        return contents.encode()

    @classmethod
    def decode(cls, blob: bytes) -> "CustomDeviceInfo":
        if _debug:
            CustomDeviceInfo._debug("decode %r", blob)

        contents = blob.decode().split(",")
        if _debug:
            CustomDeviceInfo._debug("    - contents: %r", contents)

        device_instance = int(contents[0])
        device_address = Address(contents[1])

        device_info = cls(device_instance, device_address)
        device_info.max_apdu_length_accepted = int(contents[2])
        device_info.segmentation_supported = Segmentation(contents[3])
        device_info.vendor_identifier = int(contents[4])

        return device_info


@bacpypes_debugging
class CustomDeviceInfoCache(DeviceInfoCache):
    _debug: Callable[..., None]

    def __init__(self):
        if _debug:
            CustomDeviceInfoCache._debug("__init__")
        super().__init__(device_info_class=CustomDeviceInfo)

    async def get_device_info(self, addr: Union[Address, int]) -> Optional[DeviceInfo]:
        """
        Get the device information about the device from an address.
        """
        if _debug:
            CustomDeviceInfoCache._debug("get_device_info %r", addr)

        # build a key
        if isinstance(addr, Address):
            device_info_key = f"bacnet:dev:address:{addr}"
        elif isinstance(addr, int):
            device_info_key = f"bacnet:dev:instance:{addr}"
        else:
            raise TypeError("address or device instance")
        if _debug:
            CustomDeviceInfoCache._debug("    - device_info_key: %r", device_info_key)

        # ask redis for the I-Am contents
        p = redis.pipeline()
        p.get(device_info_key)
        p.expire(device_info_key, DEVICE_INFO_CACHE_EXPIRE)
        device_info_blob, cache_expire = await p.execute()

        if _debug:
            CustomDeviceInfoCache._debug(
                "    - device_info_blob: %r, %r", device_info_blob, cache_expire
            )
        if not device_info_blob:
            return None

        device_info = CustomDeviceInfo.decode(device_info_blob)
        if _debug:
            CustomDeviceInfoCache._debug("    - device_info: %r", device_info)

        return device_info

    async def set_device_info(self, apdu: IAmRequest):
        """
        Create/update a device information record based on the contents of an
        IAmRequest and put it in the cache.
        """
        if _debug:
            CustomDeviceInfoCache._debug("set_device_info %r", apdu)

        # get the primary keys
        device_address = apdu.pduSource
        device_instance = apdu.iAmDeviceIdentifier[1]

        # build the keys
        device_address_key = f"bacnet:dev:address:{device_address}"
        if _debug:
            CustomDeviceInfoCache._debug(
                "    - device_address_key: %r", device_address_key
            )
        device_instance_key = f"bacnet:dev:instance:{device_instance}"
        if _debug:
            CustomDeviceInfoCache._debug(
                "    - device_instance_key: %r", device_instance_key
            )

        # get the primary keys
        device_address = apdu.pduSource
        device_instance = apdu.iAmDeviceIdentifier[1]

        # create an entry
        device_info = self.device_info_class(device_instance, device_address)
        device_info.deviceIdentifier = device_instance
        device_info.address = device_address

        # update record contents
        device_info.max_apdu_length_accepted = apdu.maxAPDULengthAccepted
        device_info.segmentation_supported = apdu.segmentationSupported
        device_info.vendor_identifier = apdu.vendorID

        # turn the apdu back into bytes
        device_info_blob = device_info.encode()

        # update redis
        p = redis.pipeline()
        p.set(device_address_key, device_info_blob, ex=DEVICE_INFO_CACHE_EXPIRE)
        p.set(device_instance_key, device_info_blob, ex=DEVICE_INFO_CACHE_EXPIRE)
        await p.execute()


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


@bacpypes_debugging
class CmdShell(Cmd):
    """
    Command Shell
    """

    _debug: Callable[..., None]

    async def do_whois(
        self,
        address: Address = None,
        low_limit: int = None,
        high_limit: int = None,
    ) -> None:
        """
        Send a Who-Is request and wait for the response(s).

        usage: whois [ address [ low_limit high_limit ] ]
        """
        if _debug:
            CmdShell._debug("do_whois %r %r %r", address, low_limit, high_limit)

        i_ams = await app.who_is(low_limit, high_limit, address)
        if not i_ams:
            await self.response("No response(s)")
        else:
            for i_am in i_ams:
                if _debug:
                    CmdShell._debug("    - i_am: %r", i_am)
                await self.response(f"{i_am.iAmDeviceIdentifier[1]} {i_am.pduSource}")

    async def do_wirtn(self, address: Address = None, network: int = None) -> None:
        """
        Who Is Router To Network

        usage: wirtn [ address [ network ] ]
        """
        if _debug:
            CmdShell._debug("do_wirtn %r %r", address, network)
        assert app.nse

        result_list: List[
            Tuple[NetworkAdapter, IAmRouterToNetwork]
        ] = await app.nse.who_is_router_to_network(destination=address, network=network)
        if _debug:
            CmdShell._debug("    - result_list: %r", result_list)
        if not result_list:
            raise RuntimeError("no response")

        report = []
        previous_source = None
        for adapter, i_am_router_to_network in result_list:
            if _debug:
                CmdShell._debug("    - adapter: %r", adapter)
                CmdShell._debug(
                    "    - i_am_router_to_network: %r", i_am_router_to_network
                )

            if i_am_router_to_network.npduSADR:
                npdu_source = i_am_router_to_network.npduSADR
                npdu_source.addrRoute = i_am_router_to_network.pduSource
            else:
                npdu_source = i_am_router_to_network.pduSource

            if (not previous_source) or (npdu_source != previous_source):
                report.append(str(npdu_source))
                previous_source = npdu_source

            report.append(
                "    "
                + ", ".join(
                    str(dnet) for dnet in i_am_router_to_network.iartnNetworkList
                )
            )

        await self.response("\n".join(report))

    async def do_info(self, addr: str) -> None:
        """
        Get device info from the cache

        usage: info ( address | instance )
        """
        if _debug:
            CmdShell._debug("do_info %r", addr)

        if addr.isdigit():
            addr = int(addr)
        else:
            addr = Address(addr)

        device_info = await app.device_info_cache.get_device_info(addr)
        await self.response(repr(device_info))


async def main() -> None:
    global app, redis

    app = None
    try:
        args = SimpleArgumentParser().parse_args()
        if _debug:
            _log.debug("args: %r", args)

        # connect to Redis
        redis = aioredis.from_url("redis://localhost:6379/0")
        await redis.ping()

        # build a very small stack
        console = Console()
        cmd = CmdShell()
        bind(console, cmd)

        # build an application
        app = Application.from_args(
            args,
            device_info_cache=CustomDeviceInfoCache(),
            # router_info_cache=CustomRouterInfoCache(),
        )
        if _debug:
            _log.debug("app: %r", app)

        # run until the console is done, canceled or EOF
        await console.fini.wait()

    finally:
        if app:
            app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if _debug:
            _log.debug("keyboard interrupt")
